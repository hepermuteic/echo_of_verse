"""Client data shapes pinned to frontend e24415f; no server save/settings service."""
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_serializer

CLIENT_POEM_ID = 'shuidiaogetou'
FRONTEND_COMMIT = 'e24415f2f5784df287fa20cb56b786e3e3c13e2f'
Dynasty = Literal['唐', '宋', '元', '明', '清']
Genre = Literal['送别', '边塞', '思乡', '山水', '田园', '咏月', '怀古', '羁旅', '咏物', '感怀']
Form = Literal['ci', 'qu', 'shi']
ArtKey = Literal['home', 'scene', 'moon', 'cup', 'shadow', 'mist', 'weicheng', 'jingting',
                 'denggao', 'fengqiao', 'momei', 'cunju', 'tianjingsha', 'linjiangxian',
                 'jihaizashi', 'rumengling', 'liangzhou']
Text = Annotated[str, Field(min_length=1, max_length=8192)]
Stanza = Annotated[list[Text], Field(min_length=1)]


class ClientContract(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)


class ClientAct(ClientContract):
    n: Text
    t: Text


class ClientImagery(ClientContract):
    name: Text
    line: Text
    clip: Text
    note: Text
    src: Text
    art: ArtKey


class ClientPoem(ClientContract):
    id: Literal['shuidiaogetou']
    title: Text
    form: Form
    author: Text
    dynasty: Dynasty
    genre: Genre
    first: Text
    preface: Text | None = None
    stanzas: list[Stanza] = Field(min_length=2, max_length=2)
    acts: list[ClientAct] | None = None
    imagery: list[ClientImagery] | None = None
    note: Text | None = None
    art: ArtKey

    @model_serializer(mode='wrap')
    def omit_absent_optional_fields(self, handler):
        data = handler(self)
        for field in ('preface', 'acts', 'imagery', 'note'):
            if data.get(field) is None:
                data.pop(field, None)
        return data


class SaveSlot(ClientContract):
    poemId: Literal['shuidiaogetou']
    lineIndex: int = Field(ge=0, le=8)
    act: int = Field(ge=0, le=2)
    savedAt: int = Field(ge=0)


Percent = Annotated[int, Field(ge=0, le=100)]
OptionIndex = Annotated[int, Field(ge=0, le=2)]


class ClientSettings(ClientContract):
    master: Percent = 80
    music: Percent = 20
    ambient: Percent = 70
    voice: Percent = 90
    mouse: Percent = 50
    size: OptionIndex = 1
    sub: OptionIndex = 0
    quality: OptionIndex = 1
    brush: bool = True
    reduce: bool = False
    subOn: bool = True
