"""Resource handoff contracts. No downloader, storage writer or new API route."""
import math
from typing import Literal

from pydantic import ConfigDict, Field, FiniteFloat, HttpUrl, field_validator, model_serializer, model_validator

from app.contracts import Contract, InputIdentifier


class AssetReference(Contract):
    asset_id: InputIdentifier
    asset_version: InputIdentifier


class ObjectLocation(Contract):
    """Server-side locator; credentials and expiring URLs do not belong here."""
    provider: Literal["minio", "oss"]
    bucket: InputIdentifier
    object_key: str = Field(min_length=1, max_length=1024)

    @field_validator("object_key")
    @classmethod
    def relative_key(cls, value):
        if value.startswith("/") or "\\" in value or any(p in ("", ".", "..") for p in value.split("/")):
            raise ValueError("Use a relative object key with no empty or traversal segments")
        return value


class AssetRecord(AssetReference):
    asset_type: Literal["prefab", "scene", "model", "audio", "texture", "material", "vfx"]
    status: Literal["declared", "ready", "retired"] = "declared"
    delivery: Literal["builtin", "addressables", "file", "godot_resource"]
    format: Literal["unity_prefab", "unity_audioclip", "unity_material", "unity_texture", "assetbundle", "glb", "wav", "ogg", "png", "tscn", "tres", "mp3"]
    resource_path: str | None = Field(default=None, max_length=1024)
    address: InputIdentifier | None = None
    catalog_url: HttpUrl | None = None
    object_location: ObjectLocation | None = None
    size_bytes: int | None = Field(default=None, gt=0, strict=True)
    sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    dependencies: list[AssetReference] = Field(default_factory=list)
    target_platform: Literal["any", "windows", "linux", "macos", "android", "ios", "webgl"] = "any"
    unity_version: InputIdentifier | None = None
    render_pipeline: Literal["urp", "builtin", "hdrp"] | None = None
    source_coordinate_system: Literal["unity_left_handed_y_up", "gltf_right_handed_y_up"] | None = None
    meters_per_unit: FiniteFloat | None = Field(default=None, gt=0)
    triangle_count: int | None = Field(default=None, ge=0, strict=True)
    content_review_status: Literal["demo_unreviewed", "reviewed"] = "demo_unreviewed"
    source: str = Field(min_length=1, max_length=2048)
    license: str = Field(min_length=1, max_length=256)

    @field_validator('resource_path', mode='before')
    @classmethod
    def godot_path(cls, value):
        if value is None:
            return value
        if not isinstance(value, str) or value != value.strip() or not value.startswith('res://'):
            raise ValueError('Godot resources require a res:// project path')
        relative = value[6:]
        if (any(c in relative for c in '\\:%?#') or any(ord(c) < 32 or ord(c) == 127 for c in relative)
                or any(part in ('', '.', '..') or part.endswith((' ', '.')) for part in relative.split('/'))):
            raise ValueError('Godot resource paths must be canonical relative project paths')
        return value

    @model_serializer(mode='wrap')
    def resource_fields(self, handler):
        data = handler(self)
        if self.delivery != 'godot_resource':
            data.pop('resource_path', None)
        else:
            for field in ('address', 'catalog_url', 'object_location', 'unity_version', 'render_pipeline',
                          'source_coordinate_system', 'meters_per_unit'):
                data.pop(field, None)
        return data

    @field_validator("catalog_url")
    @classmethod
    def public_catalog_location(cls, value):
        if value is not None and (value.username or value.password or value.query or value.fragment):
            raise ValueError("Store a stable catalog URL without credentials or signed query parameters")
        return value

    @model_validator(mode="after")
    def delivery_contract(self):
        builtin_formats = {"prefab": "unity_prefab", "model": "unity_prefab", "audio": "unity_audioclip",
                           "texture": "unity_texture", "material": "unity_material", "vfx": "unity_prefab"}
        file_formats = {"model": {"glb"}, "audio": {"wav", "ogg"}, "texture": {"png"}}
        if self.delivery == 'godot_resource':
            formats = {'scene': {'tscn'}, 'vfx': {'tscn'}, 'model': {'glb'}, 'material': {'tres'},
                       'texture': {'png'}, 'audio': {'wav', 'ogg', 'mp3'}}
            if self.format not in formats.get(self.asset_type, set()):
                raise ValueError('Unsupported Godot format for this resource type')
            if any(getattr(self, field) is not None for field in ('address', 'catalog_url', 'object_location',
                    'unity_version', 'render_pipeline', 'source_coordinate_system', 'meters_per_unit')):
                raise ValueError('Godot resources must not carry legacy/remote resource settings')
            if self.resource_path is not None and not self.resource_path.endswith('.' + self.format):
                raise ValueError('Godot resource extension must match its format')
            if self.status == 'ready' and (not self.resource_path or self.size_bytes is None or self.sha256 is None):
                raise ValueError('Ready Godot resources require path, size and SHA-256')
        elif self.resource_path is not None or self.asset_type == 'scene':
            raise ValueError('Godot fields require godot_resource delivery')
        elif self.delivery == "builtin":
            if self.format != builtin_formats.get(self.asset_type) or self.address is None:
                raise ValueError("Builtin resources require an address and a matching Unity object format")
            if self.object_location is not None or self.catalog_url is not None:
                raise ValueError("Builtin resources must not have remote locations")
        elif self.delivery == "addressables":
            if self.format != "assetbundle" or self.address is None:
                raise ValueError("Addressables require an address and assetbundle format")
            if self.status == "ready" and (self.catalog_url is None or self.target_platform == "any"
                                          or self.unity_version is None):
                raise ValueError("Ready Addressables require catalog URL, concrete platform and Unity build version")
        else:
            if self.format not in file_formats.get(self.asset_type, set()):
                raise ValueError("Unsupported file format for this resource type")
            if self.address is not None or self.catalog_url is not None:
                raise ValueError("File resources use object locations rather than Unity addresses")
            if self.asset_type == "model" and (self.source_coordinate_system != "gltf_right_handed_y_up"
                                               or self.meters_per_unit != 1):
                raise ValueError("GLB resources use the glTF coordinate system and meters")
        if self.status == "ready" and self.delivery not in ("builtin", "godot_resource"):
            if self.object_location is None or self.size_bytes is None or self.sha256 is None:
                raise ValueError("Ready remote resources require an object location, size and SHA-256")
        if self.status == "ready" and self.license.casefold() in ("pending", "unknown"):
            raise ValueError("Ready resources require a known license or rights statement")
        refs = [(d.asset_id, d.asset_version) for d in self.dependencies]
        if len(set(refs)) != len(refs) or (self.asset_id, self.asset_version) in refs:
            raise ValueError("Resource dependencies must be unique and must not reference self")
        return self


class ResourceManifest(Contract):
    model_config = ConfigDict(json_schema_extra={'allOf': [{
        'if': {'required': ['schema_version'], 'properties': {'schema_version': {'const': '1.1'}}},
        'then': {'required': ['engine'], 'properties': {'engine': {'const': 'godot'},
                 'assets': {'items': {'properties': {'delivery': {'const': 'godot_resource'}}}}}},
        'else': {'properties': {'engine': {'type': 'null'},
                 'assets': {'items': {'properties': {'delivery': {'not': {'const': 'godot_resource'}}}}}}},
    }]})
    schema_version: Literal["1.0", "1.1"] = "1.0"
    engine: Literal['godot'] | None = None
    catalog_version: InputIdentifier
    assets: list[AssetRecord] = Field(min_length=1, max_length=10000)

    @model_serializer(mode='wrap')
    def manifest_fields(self, handler):
        data = handler(self)
        if self.schema_version == '1.0':
            data.pop('engine', None)
        return data

    @model_validator(mode="after")
    def dependency_graph(self):
        godot = self.schema_version == '1.1'
        if godot != (self.engine == 'godot') or any((a.delivery == 'godot_resource') != godot for a in self.assets):
            raise ValueError('Manifest 1.1 requires Godot-only resources; legacy 1.0 must remain legacy')
        records = {(a.asset_id, a.asset_version): a for a in self.assets}
        if len(records) != len(self.assets):
            raise ValueError("Duplicate resource identity and version")
        graph = {}
        for key, asset in records.items():
            graph[key] = [(d.asset_id, d.asset_version) for d in asset.dependencies]
            for ref in graph[key]:
                if ref not in records:
                    raise ValueError("Dependency is missing from this manifest")
                if asset.status == "ready" and records[ref].status != "ready":
                    raise ValueError("Ready resources require ready dependencies")
        # Iterative topological traversal avoids recursion limits on long chains.
        degree = {key: len(refs) for key, refs in graph.items()}
        parents = {key: [] for key in graph}
        for key, refs in graph.items():
            for ref in refs:
                parents[ref].append(key)
        available = [key for key, n in degree.items() if n == 0]
        visited = 0
        while available:
            key = available.pop()
            visited += 1
            for parent in parents[key]:
                degree[parent] -= 1
                if degree[parent] == 0:
                    available.append(parent)
        if visited != len(graph):
            raise ValueError("Resource dependency cycle")
        return self


def resource_compatible(record, *, godot):
    """One compatibility rule for direct references and their transitive dependencies."""
    if record.target_platform not in ('any', 'windows'):
        return False
    if godot:
        return record.delivery == 'godot_resource'
    return record.delivery == 'builtin' and record.render_pipeline in (None, 'urp')


class EntityPlacement(Contract):
    """Placement contract used by offline binding registries."""
    id: InputIdentifier
    asset_id: InputIdentifier
    asset_version: InputIdentifier
    position: tuple[FiniteFloat, FiniteFloat, FiniteFloat]
    rotation: tuple[FiniteFloat, FiniteFloat, FiniteFloat, FiniteFloat] = (0, 0, 0, 1)
    scale: tuple[FiniteFloat, FiniteFloat, FiniteFloat] = (1, 1, 1)

    @field_validator("rotation")
    @classmethod
    def unit_quaternion(cls, value):
        if not math.isclose(sum(v * v for v in value), 1, abs_tol=1e-5):
            raise ValueError("Rotation must be a normalized quaternion in x,y,z,w order")
        return value

    @field_validator("scale")
    @classmethod
    def positive_scale(cls, value):
        if any(v <= 0 for v in value):
            raise ValueError("Scale components must be positive; mirrored meshes require an asset variant")
        return value
