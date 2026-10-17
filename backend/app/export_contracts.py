"""Regenerate machine-readable contracts and current offline client examples; no database access."""
import argparse
import json
from pathlib import Path

from app.client_content import client_documents
from app.content import ROOT, source_dir
from app.demo_content import load_source, validate_pack
from app.demo_models import ContentPack, JourneySnapshot
from app.main import app
from app.resources import EntityPlacement, ResourceManifest
from app.ai_authoring.models import KnowledgeBase, AnalysisReport, ValidationReport
from app.ai_authoring.scene import SceneReport, SceneAuditReport
from app.ai_authoring.feedback import FeedbackReport


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'examples')
    args = parser.parse_args(argv)
    pack, manifest = load_source(source_dir())
    report = validate_pack(pack, manifest)
    if not report['ok']:
        raise ValueError('Refusing examples from invalid content')
    documents = client_documents(pack)
    documents.update({name: model.model_json_schema() for name, model in (
        ('content-pack.schema.json', ContentPack), ('journey-snapshot.schema.json', JourneySnapshot),
        ('resource-manifest.schema.json', ResourceManifest), ('entity-placement.schema.json', EntityPlacement))})
    documents['openapi.json'] = app.openapi()
    documents.update({name: model.model_json_schema() for name, model in (
        ('ai-knowledge.schema.json', KnowledgeBase), ('ai-analysis.schema.json', AnalysisReport),
        ('ai-validation.schema.json', ValidationReport), ('ai-scene.schema.json', SceneReport),
        ('ai-scene-audit.schema.json', SceneAuditReport), ('ai-feedback.schema.json', FeedbackReport))})
    args.output.mkdir(parents=True, exist_ok=True)
    for name, value in documents.items():
        (args.output / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'Wrote {len(documents)} contracts/examples to {args.output}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
