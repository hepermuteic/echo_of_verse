"""One projection used by HTTP and offline export; never infer game events from UI rows."""
from app.client_contracts import ClientAct, ClientImagery, ClientPoem, ClientSettings, SaveSlot


def project_client_poem(pack):
    from app.content import POEM_ID
    view = pack.clientPresentation
    if view is None or pack.poem.poemId != POEM_ID:
        raise ValueError('No client presentation for this work')
    segments = {s.segmentId: s for s in pack.poem.segments}
    ordered = [s.segmentId for s in sorted(pack.poem.segments, key=lambda s: s.order)]
    grouped = [identity for group in view.stanzaSegmentIds for identity in group]
    if any(not group for group in view.stanzaSegmentIds) or grouped != ordered or len(grouped) != 8:
        raise ValueError('Client stanzas must cover all eight stable segments once in order')
    acts = sorted(pack.acts, key=lambda a: a.order)
    if [a.actId for a in view.acts] != [a.actId for a in acts]:
        raise ValueError('Client act labels must bind the three ordered acts')
    texts = {t.textId: t for t in pack.texts}
    def text(identity):
        entry = texts[identity]
        if not entry.required:
            raise ValueError('Client-visible text must participate in release review')
        return entry.zh
    return ClientPoem(
        id=view.id, title=view.title, form=view.form, author=pack.poem.author,
        dynasty=view.dynasty, genre=view.genre, first=view.first, preface=pack.poem.preface,
        stanzas=[[segments[identity].text for identity in group] for group in view.stanzaSegmentIds],
        acts=[ClientAct(n=binding.n, t=act.title) for binding, act in zip(view.acts, acts)],
        imagery=[ClientImagery(name=i.name, line=text(i.lineTextId), clip=text(i.clipTextId),
                               note=text(i.noteTextId), src=text(i.sourceTextId), art=i.art)
                 for i in view.imagery],
        note=text(view.noteTextId) if view.noteTextId else None, art=view.art)


def client_documents(pack):
    poem = project_client_poem(pack)
    return {
        'client-poems.json': [poem.model_dump(mode='json', exclude_none=True)],
        'client-poem.schema.json': ClientPoem.model_json_schema(),
        'client-save-slot.schema.json': SaveSlot.model_json_schema(),
        'client-settings.schema.json': ClientSettings.model_json_schema(),
        'client-default-settings.json': ClientSettings().model_dump(mode='json'),
    }
