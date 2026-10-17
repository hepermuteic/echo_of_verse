"""Explicit AI CLI; model calls are never made by API startup or ordinary checks."""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from pydantic import ValidationError, TypeAdapter

from app.ai_authoring.artifacts import bundle, readable, write_json
from app.ai_authoring.models import AnalysisReport, Claim, ValidationReport
from app.ai_authoring.provider import AuthoringError, Budget, DeepSeek
from app.ai_authoring.retrieval import load_retrieval
from app.ai_authoring.service import (analysis_claims, analyze, extract_content_claims, read_pack,
                                      validate_claims, verify_analysis)
from app.configuration import ROOT, load_config
from app.ai_authoring.scene import generate_scene, audit_scene, compile_scene
from app.demo_content import export_pack
from app.resources import ResourceManifest
from app.ai_authoring.feedback import generate_feedback
from app.demo_models import JourneySnapshot

PROJECT = ROOT.parent
KNOWLEDGE = ROOT / 'knowledge/shuidiaogetou'
DEFAULT_BUDGET = PROJECT / 'work/ai-rag-261017/deepseek-budget.json'


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['build-index', 'analyze', 'validate', 'run', 'generate-scene', 'feedback'])
    parser.add_argument('--source', type=Path, default=ROOT / 'content/shuidiaogetou-3')
    parser.add_argument('--corpus', type=Path, default=KNOWLEDGE / 'corpus.json')
    parser.add_argument('--dictionary', type=Path, default=KNOWLEDGE / 'dictionary.txt')
    parser.add_argument('--index', type=Path, help='Previously built index.json; verify before using')
    parser.add_argument('--analysis', type=Path, help='Analysis JSON to validate; only with validate')
    parser.add_argument('--validation', type=Path, help='Validated RAG report; required with generate-scene')
    parser.add_argument('--with-scene', action='store_true', help='Extend run through LLM scene generation, audit, and draft handoff')
    parser.add_argument('--journey', type=Path, help='JourneySnapshot or explicit {synthetic:true,input:...} reference fixture')
    parser.add_argument('--claims', type=Path, help='Explicit Claim[] JSON; only with validate')
    parser.add_argument('--config', type=Path, default=ROOT / 'config/ai-authoring.example.toml')
    parser.add_argument('--output', type=Path, default=PROJECT / 'outputs/ai-drafts/shuidiaogetou')
    parser.add_argument('--run-id', default=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ-') + uuid4().hex[:8])
    parser.add_argument('--allow-model-calls', action='store_true', help='Explicitly permit billed DeepSeek requests')
    parser.add_argument('--budget-ledger', type=Path, default=DEFAULT_BUDGET,
                        help='A separately authorized test round; never rotate or reset the first-round ledger automatically')
    args = parser.parse_args(argv)
    if args.analysis and args.command not in ('validate', 'generate-scene'):
        parser.error('--analysis requires validate or generate-scene')
    if args.claims and args.command != 'validate':
        parser.error('--analysis/--claims require validate')
    if args.command == 'generate-scene' and (not args.analysis or not args.validation):
        parser.error('generate-scene requires --analysis and --validation')
    if args.validation and args.command != 'generate-scene':
        parser.error('--validation requires generate-scene')
    if args.with_scene and args.command != 'run':
        parser.error('--with-scene requires run')
    if (args.command == 'feedback') != bool(args.journey):
        parser.error('--journey is required only with feedback')
    if args.analysis and args.claims:
        parser.error('Choose either --analysis or --claims')
    code = 0
    status = {'schemaVersion': '1.0', 'command': args.command, 'status': 'failed',
              'publication': 'draft', 'humanReview': 'unreviewed', 'requestLimit': 20,
              'budgetLedger': str(args.budget_ledger), 'liveAcceptance': 'not_performed'}
    analysis = validation = provider = None
    try:
        with bundle(args.output, args.run_id) as directory:
            try:
                retrieval = load_retrieval(args.corpus, args.dictionary, args.index)
                write_json(directory, 'index.json', retrieval.document())
                status['corpusDigest'] = retrieval.corpus_digest
                if args.command != 'build-index':
                    pack = read_pack(args.source)
                    if args.analysis:
                        analysis = AnalysisReport.model_validate_json(args.analysis.read_text(encoding='utf-8'))
                        verify_analysis(analysis, pack, retrieval)
                    if args.validation:
                        validation = ValidationReport.model_validate_json(args.validation.read_text(encoding='utf-8'))
                    claims = TypeAdapter(list[Claim]).validate_json(args.claims.read_text(encoding='utf-8')) if args.claims else None
                    if not args.allow_model_calls:
                        raise AuthoringError('MODEL_CALLS_NOT_AUTHORIZED')
                    config = load_config(args.config)
                    provider = DeepSeek(config.llm, Budget(args.budget_ledger))
                    if args.command == 'feedback':
                        raw = json.loads(args.journey.read_text(encoding='utf-8'))
                        synthetic = isinstance(raw, dict) and raw.get('synthetic') is True
                        snapshot = JourneySnapshot.model_validate(raw['input'] if synthetic else raw)
                        feedback = generate_feedback(pack, snapshot, provider, synthetic=synthetic)
                        write_json(directory, 'poetic-feedback.json', feedback)
                    if args.command in ('analyze', 'run'):
                        analysis = analyze(pack, retrieval, provider)
                    if analysis:
                        write_json(directory, 'analysis.json', analysis)
                    if args.command in ('validate', 'run'):
                        if claims is None:
                            claims = analysis_claims(analysis) if analysis else []
                            # run checks generated analysis AND existing cultural explanation.
                            if args.command == 'run' or analysis is None:
                                claims += extract_content_claims(pack, provider)
                        validation = validate_claims(pack, retrieval, provider, claims)
                        write_json(directory, 'validation.json', validation)
                    if args.with_scene or args.command == 'generate-scene':
                        manifest = ResourceManifest.model_validate_json((args.source / 'resource-manifest.json').read_text(encoding='utf-8'))
                        scene = generate_scene(pack, manifest, retrieval, analysis, validation, provider)
                        write_json(directory, 'scene-blueprint.json', scene)
                        audit = audit_scene(scene, pack, validation, provider)
                        write_json(directory, 'scene-cultural-audit.json', audit)
                        candidate, checks = compile_scene(scene, pack, manifest, audit)
                        write_json(directory, 'generated-content-validation.json', checks)
                        exported = export_pack(candidate, manifest, directory / 'engine-handoff')
                        if not exported['ok']:
                            raise AuthoringError('GENERATED_HANDOFF_FAILED')
                        status['generatedContentVersion'] = candidate.contentVersion
                        status['engineImportStatus'] = 'unverified'
                    status['liveAcceptance'] = 'provider_flow_completed' if provider.usage else 'not_performed'
                status['status'] = 'completed'
            except AuthoringError as exc:
                status['errorCode'] = exc.code
                code = 1
            except (ValueError, OSError, KeyError, TypeError, ValidationError):
                # Do not echo raw validation/provider strings, config paths, or secret inputs.
                status['errorCode'] = 'INVALID_INPUT_OR_FILESYSTEM'
                code = 2
            if provider:
                status['usage'] = [u.model_dump() for u in provider.usage]
                status['diagnostics'] = provider.diagnostics
                if code and provider.usage:
                    status['liveAcceptance'] = 'provider_flow_failed'
            write_json(directory, 'run.json', status)
            (directory / 'REPORT.md').write_text(readable(analysis, validation, status['status']), encoding='utf-8')
    except (AuthoringError, ValueError, OSError):
        print(json.dumps({'ok': False, 'code': 'OUTPUT_UNAVAILABLE_OR_EXISTS'}))
        return 2
    print(json.dumps({'ok': code == 0, 'output': str((args.output / args.run_id).resolve()), **status}, ensure_ascii=False))
    return code


if __name__ == '__main__':
    raise SystemExit(main())
