from typing import Any

from pydantic import BaseModel, Field, field_validator


class CreateModelRequest(BaseModel):
    name: str = Field(default="untitled")


class ModelInfo(BaseModel):
    model_id: str
    name: str
    dirty: bool = False


class EditAttributesRequest(BaseModel):
    guid: str
    attributes: dict[str, Any]


class EditPsetRequest(BaseModel):
    guid: str
    pset_name: str
    properties: dict[str, Any]


class CreateWallRequest(BaseModel):
    name: str | None = None
    length: float = 5.0
    height: float = 3.0
    thickness: float = 0.2
    # ponto inicial (m)
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0


class DeleteEntityRequest(BaseModel):
    guid: str


# ----- geometria 3D (coordenadas IFC: Z-up, metros) -----


class CreateWallGeomRequest(BaseModel):
    name: str | None = None
    length: float = Field(default=5.0, gt=0)
    height: float = Field(default=3.0, gt=0)
    thickness: float = Field(default=0.2, gt=0)
    position: list[float] = Field(default=[0.0, 0.0, 0.0], min_length=3, max_length=3)
    rotation_z: float = 0.0  # radianos, em torno de Z
    storey_guid: str | None = None


class EditPlacementRequest(BaseModel):
    guid: str
    # absoluto: matrix[16] OU position(+rotation_z). relativo (gizmo): translate
    # e/ou rotate_z (delta em radianos). Tudo em metros / radianos.
    matrix: list[float] | None = Field(default=None, min_length=16, max_length=16)
    position: list[float] | None = Field(default=None, min_length=3, max_length=3)
    rotation_z: float | None = None
    translate: list[float] | None = Field(default=None, min_length=3, max_length=3)
    rotate_z: float | None = None
    rotation_matrix: list[float] | None = Field(default=None, min_length=9, max_length=9)
    rotation_center: list[float] | None = Field(default=None, min_length=3, max_length=3)


class EditDimensionsRequest(BaseModel):
    guid: str
    length: float = Field(gt=0)
    height: float = Field(gt=0)
    thickness: float = Field(gt=0)


class CreateSlabRequest(BaseModel):
    name: str | None = None
    length: float = Field(default=4.0, gt=0)
    width: float = Field(default=3.0, gt=0)
    thickness: float = Field(default=0.25, gt=0)
    polyline: list[list[float]] | None = Field(default=None, min_length=3)
    position: list[float] = Field(default=[0.0, 0.0, 0.0], min_length=3, max_length=3)
    rotation_z: float = 0.0
    storey_guid: str | None = None


class CreateColumnRequest(BaseModel):
    name: str | None = None
    width: float = Field(default=0.4, gt=0)
    depth: float = Field(default=0.4, gt=0)
    height: float = Field(default=3.0, gt=0)
    position: list[float] = Field(default=[0.0, 0.0, 0.0], min_length=3, max_length=3)
    rotation_z: float = 0.0
    storey_guid: str | None = None


class CreateBeamRequest(BaseModel):
    name: str | None = None
    width: float = Field(default=0.2, gt=0)
    depth: float = Field(default=0.3, gt=0)
    length: float = Field(default=5.0, gt=0)
    position: list[float] = Field(default=[0.0, 0.0, 0.0], min_length=3, max_length=3)
    rotation_z: float = 0.0
    storey_guid: str | None = None


# ----- estrutura espacial -----


class StoreySpec(BaseModel):
    name: str = "Level"
    elevation: float = 0.0


class SpatialBootstrapRequest(BaseModel):
    site_name: str = "Site"
    building_name: str = "Building"
    storeys: list[StoreySpec] | None = None


class AssignContainerRequest(BaseModel):
    guid: str
    container_guid: str


# ----- níveis (IfcBuildingStorey como datum) -----


class LevelRequest(BaseModel):
    name: str = "Level"
    elevation: float = 0.0  # cota Z em metros


class LevelPatch(BaseModel):
    name: str | None = None
    elevation: float | None = None


# ----- grids (IfcGrid + IfcGridAxis) -----


class GridAxisU(BaseModel):
    tag: str
    x: float  # posição do eixo U ao longo de X (m)


class GridAxisV(BaseModel):
    tag: str
    y: float  # posição do eixo V ao longo de Y (m)


class GridRequest(BaseModel):
    name: str | None = None
    u: list[GridAxisU] = Field(default_factory=list)
    v: list[GridAxisV] = Field(default_factory=list)
    extent: float | None = None  # meia-largura das linhas (m); auto se None


# ----- telhado (IfcRoof) -----

# IfcRoofTypeEnum — IFC4x3
# https://ifc43-docs.standards.buildingsmart.org/IFC/RELEASE/IFC4x3/HTML/lexical/IfcRoofTypeEnum.htm
ROOF_TYPE_ENUM = {
    "FLAT_ROOF", "SHED_ROOF", "GABLE_ROOF", "HIP_ROOF", "HIPPED_GABLE_ROOF",
    "GAMBREL_ROOF", "MANSARD_ROOF", "BARREL_ROOF", "RAINBOW_ROOF",
    "BUTTERFLY_ROOF", "PAVILION_ROOF", "DOME_ROOF", "FREEFORM",
    "USERDEFINED", "NOTDEFINED",
}


class RoofFace(BaseModel):
    """Uma face planar do telhado definida por seus vértices 3D (metros, Z-up)."""
    vertices: list[list[float]] = Field(min_length=3)
    edge_index: int = 0
    angle_deg: float = 30.0


class CreateRoofRequest(BaseModel):
    name: str | None = None
    faces: list[RoofFace] = Field(min_length=1)
    footprint: list[list[float]] | None = None  # [[x,y,z], ...] contorno original
    base_z: float = 0.0                          # Z da base (beiral mais baixo)
    storey_guid: str | None = None

    # ── Atributos IfcRoof (IFC4x3) ────────────────────────────────────────────
    description: str | None = None               # IfcRoot.Description
    object_type: str | None = None               # IfcObject.ObjectType (se USERDEFINED)
    tag: str | None = None                       # IfcElement.Tag
    predefined_type: str = "FREEFORM"            # IfcRoofTypeEnum

    # ── Pset_RoofCommon (IFC4x3) ─────────────────────────────────────────────
    reference: str | None = None                 # Reference (IfcIdentifier)
    status: str | None = None                    # NEW | EXISTING | DEMOLISH | TEMPORARY
    acoustic_rating: str | None = None           # AcousticRating (IfcLabel)
    fire_rating: str | None = None               # FireRating (IfcLabel)
    is_external: bool = True                     # IsExternal (IfcBoolean)
    thermal_transmittance: float | None = None   # ThermalTransmittance (W/m²K)
    load_bearing: bool = False                   # LoadBearing (IfcBoolean)

    # ── extras de inclinação (não normativos, mantidos p/ compat.) ──────────
    pitch_min_deg: float | None = None           # ângulo mínimo entre as faces
    pitch_max_deg: float | None = None           # ângulo máximo entre as faces
    thickness: float = 0.1                       # espessura do telhado (m)

    @field_validator("predefined_type")
    @classmethod
    def _validate_predefined_type(cls, v: str) -> str:
        v = (v or "FREEFORM").upper()
        if v not in ROOF_TYPE_ENUM:
            raise ValueError(
                f"predefined_type inválido: {v!r}. Valores: {sorted(ROOF_TYPE_ENUM)}"
            )
        return v
