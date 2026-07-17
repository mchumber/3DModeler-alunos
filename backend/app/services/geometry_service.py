"""Criação e edição de geometria paramétrica IFC (Fase 1+2).

Toda manipulação de forma e posição passa por `ifcopenshell.api` para preservar
inverses e manter o arquivo válido. Coordenadas são sempre IFC (Z-up, metros).

Toda função que muta o modelo usa `with mutate(entry) as f:` (lock + snapshot de
undo + dirty). Para adicionar uma geometria nova, copie `create_column` e ajuste
a representação — ver estrutura_pedagogica_backend.md.
"""
from __future__ import annotations

import math

import numpy as np
import ifcopenshell
import ifcopenshell.api
import ifcopenshell.util.placement
import ifcopenshell.util.representation
import ifcopenshell.util.unit

from app.services._mutation import mutate
from app.services.ifc_service import ModelEntry


def get_body_context(f: ifcopenshell.file):
    """Get-or-create o contexto geométrico Model/Body/MODEL_VIEW.

    Modelos carregados de disco já costumam ter um; modelos criados em branco
    (`create_blank`) não. Esta função cobre os dois casos.
    """
    body = ifcopenshell.util.representation.get_context(
        f, "Model", "Body", "MODEL_VIEW"
    )
    if body is not None:
        return body
    parent = ifcopenshell.util.representation.get_context(f, "Model")
    if parent is None:
        parent = ifcopenshell.api.run(
            "context.add_context", f, context_type="Model"
        )
    return ifcopenshell.api.run(
        "context.add_context",
        f,
        context_type="Model",
        context_identifier="Body",
        target_view="MODEL_VIEW",
        parent=parent,
    )


def matrix_from(position=(0.0, 0.0, 0.0), rotation_z: float = 0.0) -> np.ndarray:
    """Monta uma matriz 4x4 (rotação em torno de Z + translação), em radianos."""
    c, s = math.cos(rotation_z), math.sin(rotation_z)
    m = np.eye(4)
    m[0, 0], m[0, 1] = c, -s
    m[1, 0], m[1, 1] = s, c
    m[0, 3], m[1, 3], m[2, 3] = position
    return m


def _assign_storey(f, product, storey_guid: str | None):
    if not storey_guid:
        return
    storey = f.by_guid(storey_guid)
    ifcopenshell.api.run(
        "spatial.assign_container",
        f,
        products=[product],
        relating_structure=storey,
    )


def place_product(f, product, matrix, storey_guid: str | None = None) -> None:
    """Aplica o placement (matriz 4x4, metros) e associa ao storey, se houver.

    Centraliza os dois últimos passos comuns a toda geometria criada.
    """
    ifcopenshell.api.run(
        "geometry.edit_object_placement", f, product=product, matrix=matrix
    )
    _assign_storey(f, product, storey_guid)


def rect_profile(f, width: float, depth: float):
    """IfcRectangleProfileDef nas unidades do arquivo (converte metros→unidade)."""
    scale = ifcopenshell.util.unit.calculate_unit_scale(f)  # file unit -> m
    return f.create_entity(
        "IfcRectangleProfileDef",
        ProfileType="AREA",
        XDim=width / scale,
        YDim=depth / scale,
    )


def create_wall(
    entry: ModelEntry,
    name: str | None,
    length: float,
    height: float,
    thickness: float,
    position=(0.0, 0.0, 0.0),
    rotation_z: float = 0.0,
    storey_guid: str | None = None,
) -> ifcopenshell.entity_instance:
    """Cria um IfcWall com representação extrudada e placement."""
    with mutate(entry) as f:
        body = get_body_context(f)
        wall = ifcopenshell.api.run(
            "root.create_entity", f, ifc_class="IfcWall", name=name
        )
        rep = ifcopenshell.api.run(
            "geometry.add_wall_representation",
            f,
            context=body,
            length=length,
            height=height,
            thickness=thickness,
        )
        ifcopenshell.api.run(
            "geometry.assign_representation", f, product=wall, representation=rep
        )
        place_product(f, wall, matrix_from(position, rotation_z), storey_guid)
    return wall


def create_slab(
    entry: ModelEntry,
    name: str | None,
    length: float,
    width: float,
    thickness: float,
    polyline: list[list[float]] | None = None,
    position=(0.0, 0.0, 0.0),
    rotation_z: float = 0.0,
    storey_guid: str | None = None,
) -> ifcopenshell.entity_instance:
    """Cria um IfcSlab extrudado a partir do placement local.

    Se `polyline` for informada, ela define o contorno 2D local da laje.
    Caso contrario, usa o retangulo parametrico `length` x `width`.
    """
    with mutate(entry) as f:
        body = get_body_context(f)
        slab = ifcopenshell.api.run(
            "root.create_entity", f, ifc_class="IfcSlab", name=name
        )
        if polyline is None:
            slab_polyline = [(0.0, 0.0), (length, 0.0), (length, width), (0.0, width)]
        else:
            if len(polyline) < 3:
                raise ValueError("polyline da laje precisa de ao menos 3 pontos")
            slab_polyline = []
            for point in polyline:
                if len(point) < 2:
                    raise ValueError("cada ponto da polyline precisa ter x e y")
                slab_polyline.append((float(point[0]), float(point[1])))
        rep = ifcopenshell.api.run(
            "geometry.add_slab_representation",
            f,
            context=body,
            depth=thickness,
            polyline=slab_polyline,
        )
        ifcopenshell.api.run(
            "geometry.assign_representation", f, product=slab, representation=rep
        )
        place_product(f, slab, matrix_from(position, rotation_z), storey_guid)
    return slab


def create_column(
    entry: ModelEntry,
    name: str | None,
    width: float,
    depth: float,
    height: float,
    position=(0.0, 0.0, 0.0),
    rotation_z: float = 0.0,
    storey_guid: str | None = None,
) -> ifcopenshell.entity_instance:
    """Cria um IfcColumn de seção retangular extrudada na vertical (Z)."""
    with mutate(entry) as f:
        body = get_body_context(f)
        column = ifcopenshell.api.run(
            "root.create_entity", f, ifc_class="IfcColumn", name=name
        )
        profile = rect_profile(f, width, depth)
        rep = ifcopenshell.api.run(
            "geometry.add_profile_representation",
            f,
            context=body,
            profile=profile,
            depth=height,
        )
        ifcopenshell.api.run(
            "geometry.assign_representation", f, product=column, representation=rep
        )
        place_product(f, column, matrix_from(position, rotation_z), storey_guid)
    return column


def create_beam(
    entry: ModelEntry,
    name: str | None,
    width: float,
    depth: float,
    length: float,
    position=(0.0, 0.0, 0.0),
    rotation_z: float = 0.0,
    storey_guid: str | None = None,
) -> ifcopenshell.entity_instance:
    """Cria um IfcBeam de seção retangular extrudada na horizontal (eixo X).

    O perfil é extrudado ao longo do +Z local; o placement aplica Ry(90°) para
    deitar a viga (eixo local +Z -> +X do mundo), depois Rz(rotation_z) e a
    translação.
    """
    with mutate(entry) as f:
        body = get_body_context(f)
        beam = ifcopenshell.api.run(
            "root.create_entity", f, ifc_class="IfcBeam", name=name
        )
        profile = rect_profile(f, width, depth)
        rep = ifcopenshell.api.run(
            "geometry.add_profile_representation",
            f,
            context=body,
            profile=profile,
            depth=length,
        )
        ifcopenshell.api.run(
            "geometry.assign_representation", f, product=beam, representation=rep
        )
        # Orienta a viga: rotação cíclica dos eixos locais para o mundo —
        # X(width)->Y, Y(depth)->Z (altura), Z(extrusão=length)->X (eixo).
        # As colunas são as imagens de x,y,z locais no mundo.
        orient = np.array(
            [[0.0, 0.0, 1.0, 0.0],
             [1.0, 0.0, 0.0, 0.0],
             [0.0, 1.0, 0.0, 0.0],
             [0.0, 0.0, 0.0, 1.0]]
        )
        matrix = matrix_from(position, rotation_z) @ orient
        place_product(f, beam, matrix, storey_guid)
    return beam


def edit_placement(entry: ModelEntry, guid: str, matrix) -> None:
    """Atualiza o ObjectPlacement de um produto a partir de uma matriz 4x4.

    A matriz é absoluta e em metros (a `geometry.edit_object_placement`
    converte para as unidades do arquivo ao gravar).
    """
    m = np.array(matrix, dtype=float).reshape(4, 4)
    with mutate(entry) as f:
        inst = f.by_guid(guid)
        ifcopenshell.api.run(
            "geometry.edit_object_placement", f, product=inst, matrix=m
        )


def transform_product(
    entry: ModelEntry,
    guid: str,
    translate=None,
    rotate_z: float | None = None,
    rotation_matrix=None,
    rotation_center=None,
) -> None:
    """Compõe translação e/ou rotação Z **relativas** sobre o placement atual.

    Composição feita no servidor — onde o placement corrente é conhecido — para
    que o frontend só precise enviar o delta do gizmo. O placement bruto vem nas
    unidades do arquivo (ex.: mm); convertemos para metros antes de compor e a
    API reconverte ao gravar. A rotação é em torno da origem do objeto (eixos do
    mundo), em radianos, ou de `rotation_center` quando informado.
    """
    with mutate(entry) as f:
        scale = ifcopenshell.util.unit.calculate_unit_scale(f)  # file unit -> m
        inst = f.by_guid(guid)
        m = np.array(
            ifcopenshell.util.placement.get_local_placement(inst.ObjectPlacement),
            dtype=float,
        )
        m[:3, 3] *= scale  # unidades do arquivo -> metros
        rot = None
        if rotation_matrix is not None:
            rot = np.array(rotation_matrix, dtype=float).reshape(3, 3)
        elif rotate_z:
            c, s = math.cos(rotate_z), math.sin(rotate_z)
            rot = np.array([[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]])
        if rot is not None:
            if rotation_center is not None:
                center = np.array(rotation_center, dtype=float)
                m[:3, 3] = center + rot @ (m[:3, 3] - center)
            m[:3, :3] = rot @ m[:3, :3]
        if translate is not None:
            m[:3, 3] += np.array(translate, dtype=float)
        ifcopenshell.api.run(
            "geometry.edit_object_placement", f, product=inst, matrix=m
        )


def translate_product(entry: ModelEntry, guid: str, delta) -> None:
    """Atalho: translação relativa (metros). Ver `transform_product`."""
    transform_product(entry, guid, translate=delta)


def _polygon_area_3d(verts: list[list[float]]) -> float:
    """Área de um polígono plano 3D (método de Newell)."""
    n = len(verts)
    if n < 3:
        return 0.0
    normal = np.zeros(3)
    for i in range(n):
        a = np.array(verts[i], dtype=float)
        b = np.array(verts[(i + 1) % n], dtype=float)
        normal += np.cross(a, b)
    return float(np.linalg.norm(normal)) / 2.0


def _polygon_area_xy(verts: list[list[float]]) -> float:
    """Área projetada no plano XY (shoelace)."""
    n = len(verts)
    if n < 3:
        return 0.0
    s = 0.0
    for i in range(n):
        a, b = verts[i], verts[(i + 1) % n]
        s += a[0] * b[1] - b[0] * a[1]
    return abs(s) / 2.0


def create_roof(
    entry: ModelEntry,
    name: str | None,
    faces: list[dict],
    base_z: float = 0.0,
    thickness: float = 0.1,
    pitch_min_deg: float | None = None,
    pitch_max_deg: float | None = None,
    storey_guid: str | None = None,
    # atributos IfcRoof (IFC4x3)
    description: str | None = None,
    object_type: str | None = None,
    tag: str | None = None,
    predefined_type: str = "FREEFORM",
    # Pset_RoofCommon (IFC4x3)
    reference: str | None = None,
    status: str | None = None,
    acoustic_rating: str | None = None,
    fire_rating: str | None = None,
    is_external: bool = True,
    thermal_transmittance: float | None = None,
    load_bearing: bool = False,
) -> tuple[ifcopenshell.entity_instance, dict]:
    """Cria um IfcRoof com geometria baseada em faces planares (IfcShellBasedSurfaceModel).

    Cada entrada em `faces` é um dict com:
        vertices: [[x,y,z], ...]  — polígono plano da face (mínimo 3 pontos, metros)
        edge_index: int
        angle_deg: float

    A representação usa IfcOpenShell (superfície aberta) para que ferramentas
    IFC como BIMVision e Revit consigam visualizar o telhado sem solid-boolean.

    Atributos e psets seguem o IFC4x3:
      - IfcRoof.PredefinedType   (IfcRoofTypeEnum)
      - Pset_RoofCommon          (Reference, Status, AcousticRating, FireRating,
                                  IsExternal, ThermalTransmittance, LoadBearing)
      - Qto_RoofBaseQuantities   (GrossArea, NetArea, ProjectedArea)

    Retorna (roof, params) onde `params` é um dicionário com todos os
    parâmetros IFC efetivamente gravados (para exibição na UI).
    """
    with mutate(entry) as f:
        body = get_body_context(f)
        scale = ifcopenshell.util.unit.calculate_unit_scale(f)  # file unit → m

        def pt(xyz):
            return f.create_entity(
                "IfcCartesianPoint",
                Coordinates=[float(xyz[0]) / scale, float(xyz[1]) / scale, float(xyz[2]) / scale],
            )

        ifc_faces = []
        for face_data in faces:
            verts = face_data["vertices"]
            if len(verts) < 3:
                continue
            ifc_pts = [pt(v) for v in verts]
            poly_loop = f.create_entity("IfcPolyLoop", Polygon=ifc_pts)
            outer_bound = f.create_entity("IfcFaceOuterBound", Bound=poly_loop, Orientation=True)
            ifc_faces.append(f.create_entity("IfcFace", Bounds=[outer_bound]))

        if not ifc_faces:
            raise ValueError("Nenhuma face válida para o telhado (mínimo 3 vértices por face).")

        shell = f.create_entity("IfcOpenShell", CfsFaces=ifc_faces)
        surface_model = f.create_entity("IfcShellBasedSurfaceModel", SbsmBoundary=[shell])

        rep = f.create_entity(
            "IfcShapeRepresentation",
            ContextOfItems=body,
            RepresentationIdentifier="Body",
            RepresentationType="SurfaceModel",
            Items=[surface_model],
        )
        product_rep = f.create_entity("IfcProductDefinitionShape", Representations=[rep])

        roof = ifcopenshell.api.run(
            "root.create_entity",
            f,
            ifc_class="IfcRoof",
            name=name or "Telhado",
        )
        roof.Representation = product_rep

        # ── Atributos IfcRoof (IFC4x3) ───────────────────────────────────────
        if description:
            roof.Description = description
        if tag:
            roof.Tag = tag
        ptype = (predefined_type or "FREEFORM").upper()
        try:
            roof.PredefinedType = ptype
        except Exception:
            ptype = "NOTDEFINED"
        # ObjectType só é normativo quando PredefinedType = USERDEFINED
        if object_type:
            roof.ObjectType = object_type

        place_product(f, roof, matrix_from((0.0, 0.0, base_z)), storey_guid)

        angles = [face_data.get("angle_deg", 0) for face_data in faces]
        p_min = pitch_min_deg if pitch_min_deg is not None else (min(angles) if angles else 0)
        p_max = pitch_max_deg if pitch_max_deg is not None else (max(angles) if angles else 0)

        def _add_pset(pset_name: str, properties: dict):
            props = {k: v for k, v in properties.items() if v is not None}
            if not props:
                return
            pset = ifcopenshell.api.run("pset.add_pset", f, product=roof, name=pset_name)
            ifcopenshell.api.run("pset.edit_pset", f, pset=pset, properties=props)

        # ── Pset_RoofCommon (IFC4x3 oficial + extras de inclinação) ────────
        pset_common = {
            "Reference": reference,
            "Status": status,
            "AcousticRating": acoustic_rating,
            "FireRating": fire_rating,
            "IsExternal": bool(is_external),
            "ThermalTransmittance": float(thermal_transmittance) if thermal_transmittance is not None else None,
            "LoadBearing": bool(load_bearing),
            # extras não normativos (compatibilidade com a UI de inclinação)
            "PitchAngle": float(angles[0]) if angles else None,
            "PitchAngleMin": float(p_min),
            "PitchAngleMax": float(p_max),
            "NumberOfPitches": len(ifc_faces),
            "Thickness": float(thickness),
        }
        try:
            _add_pset("Pset_RoofCommon", pset_common)
        except Exception:
            pass  # Pset não crítico; não deve interromper a criação

        # ── Qto_RoofBaseQuantities (IFC4x3) ─────────────────────────────────
        gross_area = sum(_polygon_area_3d(fd["vertices"]) for fd in faces)
        projected_area = sum(_polygon_area_xy(fd["vertices"]) for fd in faces)
        qto = {
            "GrossArea": round(gross_area, 4),
            "NetArea": round(gross_area, 4),       # sem aberturas → Net = Gross
            "ProjectedArea": round(projected_area, 4),
        }
        try:
            qset = ifcopenshell.api.run(
                "pset.add_qto", f, product=roof, name="Qto_RoofBaseQuantities"
            )
            ifcopenshell.api.run("pset.edit_qto", f, qto=qset, properties=qto)
        except Exception:
            pass  # Qto não crítico

        params = {
            "GlobalId": roof.GlobalId,
            "Name": roof.Name,
            "Description": description,
            "ObjectType": object_type,
            "Tag": tag,
            "PredefinedType": ptype,
            "Pset_RoofCommon": {k: v for k, v in pset_common.items() if v is not None},
            "Qto_RoofBaseQuantities": qto,
        }

    return roof, params


def edit_wall_dimensions(
    entry: ModelEntry,
    guid: str,
    length: float,
    height: float,
    thickness: float,
) -> None:
    """Regenera a representação de uma parede com novas dimensões.

    Remove a representação Body anterior e cria outra; o placement é preservado.
    """
    with mutate(entry) as f:
        wall = f.by_guid(guid)
        body = get_body_context(f)
        old = ifcopenshell.util.representation.get_representation(
            wall, "Model", "Body", "MODEL_VIEW"
        )
        if old is not None:
            ifcopenshell.api.run(
                "geometry.unassign_representation",
                f,
                product=wall,
                representation=old,
            )
            ifcopenshell.api.run(
                "geometry.remove_representation", f, representation=old
            )
        rep = ifcopenshell.api.run(
            "geometry.add_wall_representation",
            f,
            context=body,
            length=length,
            height=height,
            thickness=thickness,
        )
        ifcopenshell.api.run(
            "geometry.assign_representation", f, product=wall, representation=rep
        )
