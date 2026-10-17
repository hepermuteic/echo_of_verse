"""Reproducible, local paragraph BM25; scores are relevance, never truth probabilities."""
import hashlib
from copy import deepcopy
import json
import math
import re
import unicodedata
from collections import Counter
from importlib.metadata import version
from pathlib import Path

from app.ai_authoring.models import KnowledgeBase


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def digest(value):
    return hashlib.sha256(encoded(value).encode('utf-8')).hexdigest()


class Retrieval:
    def __init__(self, corpus: KnowledgeBase, dictionary: Path):
        import jieba
        self.corpus = corpus
        self.corpus_digest = digest(corpus.model_dump(mode='json'))
        self.fingerprint = {'corpus': self.corpus_digest, 'dictionary': hashlib.sha256(dictionary.read_bytes()).hexdigest(),
                            'jieba': version('jieba'), 'baseDictionary': hashlib.sha256(Path(jieba.__file__).with_name('dict.txt').read_bytes()).hexdigest(),
                            'algorithm': 'bm25-v1-k1=1.5-b=0.75-nfkc-hmm=false'}
        self.tokenizer = jieba.Tokenizer()
        self.tokenizer.load_userdict(str(dictionary))
        self.chunks = []
        for source in corpus.sources:
            for p in source.paragraphs:
                # A paragraph remains a provenance boundary. Long paragraphs split losslessly.
                for offset in range(0, len(p.text), 600):
                    chunk = p.model_dump()
                    chunk['chunkId'] = p.chunkId if len(p.text) <= 600 else f'{p.chunkId}.{offset // 600 + 1}'
                    chunk['text'] = p.text[offset:offset + 600]
                    chunk.update(sourceId=source.sourceId, title=source.title, url=source.url,
                                 authorOrPublisher=source.authorOrPublisher, collectedAt=source.collectedAt,
                                 editionStatus=source.editionStatus, humanReview=source.humanReview)
                    self.chunks.append(chunk)
        ids = [c['chunkId'] for c in self.chunks]
        if len(ids) != len(set(ids)):
            raise ValueError('CHUNK_ID_COLLISION')
        self.terms = [Counter(self.tokens(c['text'])) for c in self.chunks]
        self.df = Counter(term for row in self.terms for term in row)
        self.avg = sum(sum(row.values()) for row in self.terms) / len(self.terms)

    def tokens(self, text):
        value = unicodedata.normalize('NFKC', text).casefold()
        return [t for t in self.tokenizer.cut_for_search(value, HMM=False) if re.search(r'[\w\u3400-\u9fff]', t)]

    def document(self):
        return deepcopy({'schemaVersion': '1.0', 'fingerprint': self.fingerprint,
                         'chunks': self.chunks, 'terms': [dict(row) for row in self.terms]})

    def verify_index(self, path):
        # Recompute from authoritative local corpus; reject stale or altered metadata AND postings.
        if json.loads(Path(path).read_text(encoding='utf-8')) != self.document():
            raise ValueError('STALE_OR_TAMPERED_INDEX')

    def search(self, query):
        ranked = []
        count = len(self.terms)
        for chunk, row in zip(self.chunks, self.terms):
            score = 0.0
            size = sum(row.values())
            # Hash randomization must not change addition order across CLI processes.
            for term in sorted(set(self.tokens(query))):
                freq = row.get(term, 0)
                if freq:
                    inverse = math.log(1 + (count - self.df[term] + .5) / (self.df[term] + .5))
                    score += inverse * freq * 2.5 / (freq + 1.5 * (.25 + .75 * size / self.avg))
            if score > 0:
                ranked.append({**chunk, 'score': round(score, 12)})
        return sorted(ranked, key=lambda c: (-c['score'], c['chunkId']))[:6]


def load_retrieval(corpus_path, dictionary_path, index_path=None):
    corpus = KnowledgeBase.model_validate_json(Path(corpus_path).read_text(encoding='utf-8'))
    retrieval = Retrieval(corpus, Path(dictionary_path))
    if index_path is not None:
        retrieval.verify_index(index_path)
    return retrieval
