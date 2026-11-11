"""Maqueta interpretativa del frente maqueta.jfif. Unidades: mm.
Ejecutar con Python + numpy, manifold3d, shapely, trimesh.
No es una fotogrametría. La geometría ornamental se construye con curvas.
"""
from pathlib import Path
import json
import math
import sys
import zipfile

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / '.deps'))
import numpy as np
import manifold3d as md
import trimesh
from shapely.geometry import Polygon, LineString
from shapely.ops import nearest_points, unary_union

OUT = ROOT / 'modelo_paso'
OUT.mkdir(exist_ok=True)
LARGO = 146.7
ANCHO = 88.0
PARED = 1.6
RELIEVE = 0.85
SEG = 32
RADIO_MAX_ORNAMENTO = 6.0  # mm; all ornamental curls remain below 8 mm.


def union(items):
    return md.Manifold.batch_boolean(items, md.OpType.Add)


def clean_specks(solid):
    # Intersecting bevels can leave micron-thin boolean debris. Keep cavities
    # and all printable solids; discard only positive specks below 0.002 mm³.
    bodies=solid.decompose()
    keep=[c for c in bodies if c.volume()<0 or c.volume()>=0.002]
    return md.Manifold.compose(keep) if len(keep)!=len(bodies) else solid


def section(geom):
    if geom.is_empty:
        return md.CrossSection()
    polygons = [geom] if geom.geom_type == 'Polygon' else list(geom.geoms)
    contours = []
    for p in polygons:
        if p.geom_type != 'Polygon':
            continue
        # CrossSection uses positive winding for the exterior.
        from shapely.geometry.polygon import orient
        p = orient(p, sign=1)
        contours.append(np.array(p.exterior.coords[:-1]))
        contours.extend(np.array(i.coords[:-1]) for i in p.interiors)
    return md.CrossSection(contours)


def poly(points):
    return section(Polygon(points).buffer(0))


def oval(x, y, a, b, n=48):
    return poly([(x+a*math.cos(t), y+b*math.sin(t))
                 for t in np.linspace(0, 2*math.pi, n, endpoint=False)])


def stroke(points, width=0.9):
    return section(LineString(points).buffer(width/2, quad_segs=5))


def raised(cs, depth=RELIEVE, start=-0.12):
    # Two nested extrusions give the carving a bevel with a robust footprint.
    base = md.Manifold.extrude(cs, depth*0.55).translate((0, 0, start))
    inner = cs.offset(-0.16, circular_segments=12)
    if inner.is_empty():
        return base
    top = md.Manifold.extrude(inner, depth*0.65).translate((0, 0, start+depth*0.45))
    return base + top


def leaf(x, y, length, width, angle):
    # Lobed acanthus leaf; the centre rib remains supported by the leaf.
    t = np.linspace(0, 1, 20)
    w = width/2 * np.sin(math.pi*t)**0.65 * (1+0.19*np.sin(7*math.pi*t))
    pts = np.vstack((np.c_[w, t*length], np.c_[-w[::-1], t[::-1]*length]))
    a = math.radians(angle)
    rot = np.array([[math.cos(a), -math.sin(a)], [math.sin(a), math.cos(a)]])
    pts = pts @ rot.T + (x, y)
    rib = np.array([[0, length*0.08], [0, length*0.82]]) @ rot.T + (x, y)
    return [raised(poly(pts), 1.05), raised(stroke(rib, 0.65), 0.45, 0.65)]


def spiral(x, y, radius, turn=1, angle=0, sy=1):
    assert 0 < radius*max(1,sy) <= RADIO_MAX_ORNAMENTO
    t = np.linspace(0, 2.65*math.pi, 86)
    r = radius*(1-t/(3.12*math.pi))
    a = math.radians(angle) + turn*t
    points = np.c_[x+r*np.cos(a), y+sy*r*np.sin(a)]
    return raised(stroke(points, 0.95), 1.05)


def medallion(x, z, small=False):
    a, b = (3.6, 4.3) if small else (3.9, 4.6)
    objects = [raised(oval(x,z,a,b), 0.55),
               raised(oval(x,z,a+1.15,b+1.15)-oval(x,z,a+0.15,b+0.15), 1.25)]
    # Oval reserve left blank; no invented religious insignia.
    inner = oval(x,z,a-1.1,b-1.1)-oval(x,z,a-1.75,b-1.75)
    objects.append(raised(inner,0.45,0.35))
    t=np.linspace(0,2*math.pi,100,endpoint=False)
    outer=poly([(x+(a+1.8+0.45*math.cos(10*v))*math.cos(v),
                 z+(b+1.8+0.45*math.cos(10*v))*math.sin(v)) for v in t])
    objects.append(raised(outer-oval(x,z,a+0.85,b+0.85),1.45))
    for sign in [-1,1]:
        objects += leaf(x+sign*(a+0.6),z-3.0,5.1,2.2,-sign*35)
        objects.append(spiral(x+sign*(a+1.3),z+3.0,2.3,sign,180 if sign>0 else 0))
        objects += leaf(x+sign*1.5,z+b-0.3,3.0,1.9,-sign*25)
    objects += leaf(x,z-b-2.9,3.7,2.6,0)
    return objects


def curled_leaf(x,z,length,width,angle,bend=1.7,lobes=4,depth=1.25):
    """Curved, lobed acanthus with a raised spine and oblique side veins."""
    t=np.linspace(0,1,36)
    centre=np.c_[bend*np.sin(t*math.pi/2),t*length]
    tangent=np.c_[bend*math.pi/2*np.cos(t*math.pi/2),np.full_like(t,length)]
    normal=np.c_[tangent[:,1],-tangent[:,0]]
    normal/=np.linalg.norm(normal,axis=1)[:,None]
    edge=width/2*np.sin(math.pi*t)**0.65*(1+0.25*np.sin(lobes*2*math.pi*t))
    outline=np.vstack((centre+normal*edge[:,None],(centre-normal*edge[:,None])[::-1]))
    a=math.radians(angle)
    rot=np.array([[math.cos(a),-math.sin(a)],[math.sin(a),math.cos(a)]])
    def place(v):return np.array(v)@rot.T+(x,z)
    result=[raised(poly(place(outline)),depth),
            raised(stroke(place(centre[2:-3]),0.65),0.4,depth*0.65)]
    for f in [0.27,0.46,0.65]:
        i=round(f*35);j=min(i+4,33)
        for sign in [-1,1]:
            vein=place([centre[i],centre[j]+sign*normal[j]*edge[j]*0.72])
            result.append(raised(stroke(vein,0.6),0.32,depth*0.63))
    return result


def compact_scroll(x,z,r,angle,turn=1,depth=1.25,width=1.1):
    assert 0.9 <= r <= RADIO_MAX_ORNAMENTO
    t=np.linspace(0,(2.05 if r>2.4 else 1.62)*math.pi,70)
    radius=np.linspace(r,0.85,len(t))
    a=math.radians(angle)+turn*t
    points=np.c_[x+radius*np.cos(a),z+radius*np.sin(a)]
    return raised(stroke(points,width),depth)


def compact_carving(side,short=False,lower=False):
    """Small, interlocking acanthus curls, composed around the central cartouche.

    Staggered radii/angles avoid an array of identical motifs. The largest
    decorative turn is 4 mm; there are no long stretched Bezier sweeps.
    """
    phase={'frente':0,'trasera':1,'derecho':2,'izquierdo':3}[side]
    elements=[]
    if lower:
        # The front follows the reference: a lace band, central pendant and
        # deeply carved corner drops. Long sides develop the same construction.
        motifs=[(10.2,24.0,2.0,160),(15.1,22.0,2.6,35),
                (20.9,24.0,2.9,130),(26.4,21.6,2.3,285),
                (31.6,24.0,2.7,85),(37.5,21.8,2.6,205),
                (12.2,18.4,1.7,25),(18.0,19.2,1.8,240),
                (28.8,18.6,2.0,155),(36.5,16.8,2.5,20),
                (38.2,12.0,2.2,190),(37.0,8.4,1.6,70)]
        if not short:
            # Two different lobed clusters extend each long flank.
            motifs=[m for m in motifs if m[0]<34]
            motifs += [(37.2,22.5,2.5,195),(43.1,24.0,2.9,65),
                       (48.8,21.8,2.4,300),(54.2,24.2,2.7,150),
                       (61.6,21.9,2.7,30),(33.0,17.7,2.6,215),
                       (33.7,13.5,2.3,70),(45.8,18.7,1.8,120),
                       (59.7,17.0,2.5,220),(62.7,12.2,2.2,35),
                       (62.2,8.2,1.8,185)]
    else:
        motifs=[(9.8,40.2,2.0,220),(10.9,54.0,2.3,55),
                (16.2,49.2,3.1,185),(21.9,55.1,2.5,10),
                (26.7,48.3,3.2,95),(17.2,41.0,2.7,315),
                (24.7,39.7,2.1,145),(30.1,55.5,1.9,260),
                (9.5,46.5,1.7,70),(22.0,45.1,1.9,255)]
        if not short:
            motifs += [(34.2,43.2,3.2,135),(37.0,54.1,2.9,260),
                       (42.9,48.7,3.4,40),(48.9,41.2,2.7,200),
                       (52.7,54.0,3.0,105),(56.0,46.8,2.1,320),
                       (43.4,39.9,1.9,70),(48.1,54.9,1.8,185),
                       (32.6,50.0,1.8,25),(38.9,40.1,1.7,295)]
    for hand in [-1,1]:
        for i,(x,z,r,angle) in enumerate(motifs):
            # Slight changes of angle and leaf fan differentiate opposite faces.
            turn=1 if (i+phase+(hand>0))%2 else -1
            angle=hand*(angle+phase*11)
            depth=1.00+0.12*((i+phase)%3)
            elements.append(compact_scroll(hand*x,z,r,angle,turn*hand,depth))
            root_angle=math.radians(angle)
            rootx=hand*x+r*math.cos(root_angle)
            rootz=z+r*math.sin(root_angle)
            length=3.7+0.45*(i%4)
            elements+=curled_leaf(rootx,rootz,length,2.4+0.3*(i%3),
                                  hand*(42+(i*37+phase*13)%240),
                                  hand*(0.8+0.25*(i%4)),3+i%3,1.15)
            if i%3==1:
                elements+=curled_leaf(hand*x,z-1.2,3.4,2.3,
                                      hand*(-45+17*i),-hand*1.0,3,1.05)
    return elements


def connect_lace(lace):
    """Join isolated leaf clusters with short 1.5 mm stems on the backing."""
    def geometry(cs):
        contours=cs.to_polygons()
        outer=max(range(len(contours)),key=lambda i:abs(Polygon(contours[i]).area))
        return Polygon(contours[outer],[c for i,c in enumerate(contours) if i!=outer]).buffer(0)
    pieces=[geometry(c) for c in lace.decompose()]
    top=max(range(len(pieces)),key=lambda i:(pieces[i].bounds[3],pieces[i].area))
    connected=pieces.pop(top)
    links=[]
    while pieces:
        i=min(range(len(pieces)),key=lambda i:connected.distance(pieces[i]))
        piece=pieces.pop(i)
        p,q=nearest_points(connected,piece)
        bridge=LineString([p,q]).buffer(0.75,quad_segs=5)
        links.append(section(bridge))
        connected=unary_union([connected,piece,bridge])
    for link in links:
        lace=lace+link
    assert len(lace.decompose())==1,'Respiradero con hojas sin unir'
    return lace,links


def rounded_points(w, h, r, n=12):
    pts=[]
    for cx,cy,start in [(w/2-r,h/2-r,0),(-w/2+r,h/2-r,90),
                         (-w/2+r,-h/2+r,180),(w/2-r,-h/2+r,270)]:
        for a in np.linspace(start,start+90,n,endpoint=False):
            t=math.radians(a)
            pts.append((cx+r*math.cos(t),cy+r*math.sin(t)))
    return np.array(pts)


def ring(w,h,r,wall,height,z):
    cs=poly(rounded_points(w,h,r))-poly(rounded_points(w-2*wall,h-2*wall,max(r-wall,0.5)))
    return md.Manifold.extrude(cs,height).translate((0,0,z))


PROFILE = [(32,72,130),(35,74,132),(43,78,136),(51,78,136),(60,74,132),(63,74,132)]


def loft_shell():
    vertices=[]
    for z,w,h in PROFILE:
        vertices.extend((x,y,z) for x,y in rounded_points(w,h,5.0))
    n=48
    faces=[]
    # Outer loft, close each end; boolean out the corresponding inner loft.
    for k in range(len(PROFILE)-1):
        for i in range(n):
            a=k*n+i;b=k*n+(i+1)%n;c=b+n;d=a+n
            faces.extend(((a,b,c),(a,c,d)))
    for i in range(1,n-1):
        faces.append((0,i+1,i))
        a=(len(PROFILE)-1)*n
        faces.append((a,a+i,a+i+1))
    def body(v):
        return md.Manifold(md.Mesh(np.array(v,dtype=np.float32),np.array(faces,dtype=np.uint32)))
    outer=body(vertices)
    inner=[]
    for z,w,h in PROFILE:
        # Inner profile runs beyond the ends to open both mouths of the shell.
        zi=z-1 if z==32 else z+1 if z==63 else z
        inner.extend((x,y,zi) for x,y in rounded_points(w-2*PARED,h-2*PARED,5-PARED))
    return outer-body(inner)


def mount_upper(obj, side):
    lengths=[p[2] if side in ('frente','trasera') else p[1] for p in PROFILE]
    def warp(v):
        u,z,d=v
        half=float(np.interp(z,[p[0] for p in PROFILE],lengths))/2
        if side=='frente': return (u,-half-d,z)
        if side=='trasera': return (-u,half+d,z)
        if side=='derecho': return (half+d,u,z)
        return (-half-d,-u,z)
    # Subdivide before bending: otherwise large cap triangles cut through the
    # convex body and swallow the centre of a medallion or a scroll.
    return obj.refine_to_length(1.1).warp(warp)


def upper_ornament(side):
    length=62 if side in ('frente','trasera') else 116
    cs=compact_carving(side,short=length==62)
    cs.extend(medallion(0,47))
    for z in [36.0,58.8]:
        cs.append(raised(stroke([(-length/2,z),(length/2,z)],0.95),0.8))
        for u in np.arange(-length/2+2,length/2,3.4):
            cs.append(raised(oval(float(u),z,0.60,0.60,16),0.65,0.45))
    # Gadroons beneath the upper cornice, each wider than one nozzle pass.
    for u in np.arange(-length/2+1.2,length/2,2.8):
        cs.append(raised(oval(float(u),61.0,0.7,1.2,24),0.8))
    # Carved scrolls continue into the rounded corner pilasters.
    if length==62:
        for sign in [-1,1]:
            cs.append(spiral(sign*30.4,49.6,3.1,sign,180 if sign>0 else 0,1.4))
            cs+=leaf(sign*30.5,40.3,7.5,3.1,-sign*16)
    # Keep the carving inside the cornices and clear of the outer corners.
    field=poly([(-length/2-2,35),(length/2+2,35),(length/2+2,62),(-length/2-2,62)])
    return mount_upper(union(cs)^md.Manifold.extrude(field,4).translate((0,0,-0.3)),side)


def arabic_lattice(outline,width):
    """Recessed lattice: eight-pointed stars alternating with diamond openings.

    5.2 mm repeat, 4.2 mm stars, approximately 0.9–1.0 mm minimum webs.
    The 1.2 mm rear layer overlaps the carved backing by 0.2 mm.
    """
    pitch=5.2
    holes=[]
    for x in np.arange(-math.ceil(width/pitch)*pitch/2,width/2+pitch,pitch):
        for z in np.arange(1.6,29+pitch,pitch):
            star=[]
            for k in range(16):
                a=k*math.pi/8
                radius=2.1 if k%2==0 else 1.58
                star.append((float(x)+radius*math.cos(a),float(z)+radius*math.sin(a)))
            holes.append(poly(star))
            cx,cz=float(x)+pitch/2,float(z)+pitch/2
            holes.append(poly([(cx-.95,cz),(cx,cz-.95),(cx+.95,cz),(cx,cz+.95)]))
    openings=md.CrossSection.batch_boolean(holes,md.OpType.Add) ^ outline.offset(-0.95)
    lattice=outline-openings
    assert len(lattice.decompose())==1,'Celosía sin continuidad'
    return md.Manifold.extrude(lattice,1.2).translate((0,0,-1.0))


def apron(side):
    short=side in ('frente','trasera')
    width=83 if short else 140
    u=np.linspace(-width/2,width/2,240)
    centres=[-0.455*width,0,0.455*width] if short else [-0.455*width,-0.235*width,0,0.235*width,0.455*width]
    low=np.full_like(u,16.7)
    for c in centres:
        low-= (13.9 if c==0 else 11.8)*np.exp(-((u-c)/(7.5 if c==0 else 6.0))**2)
    contour=[(-width/2,29.0),(width/2,29.0)]+list(zip(u[::-1],low[::-1]))
    allowed=poly(contour)
    ornaments=medallion(0,18.0,True)
    ornaments+=compact_carving(side,short=short,lower=True)
    # The photo's central cartouche descends into a pointed acanthus pendant.
    for hand in [-1,1]:
        ornaments.append(compact_scroll(hand*3.3,10.4,2.4,hand*145,hand,1.15))
        ornaments+=curled_leaf(hand*2.4,5.8,5.1,3.2,hand*28,-hand*0.9,4,1.2)
        ornaments+=curled_leaf(hand*1.2,9.5,4.2,2.8,hand*58,hand*1.0,3,1.15)
    ornaments+=curled_leaf(0,2.9,6.0,3.8,0,0.65,4,1.2)
    pattern=union(ornaments)
    # Actual lace: material follows the leaves and scrolls. The gaps are the
    # spaces between carving, instead of oval holes punched in a solid plate.
    band=poly([(-width/2,26.5),(width/2,26.5),(width/2,29),(-width/2,29)])
    lace=(pattern.project().offset(0.28,circular_segments=12)+band) ^ allowed
    lace,links=connect_lace(lace)
    base=md.Manifold.extrude(lace,PARED)
    clipping=md.Manifold.extrude(lace,5)
    carving=pattern.translate((0,0,PARED-0.02)) ^ clipping
    top_rib=raised(stroke([(-width/2,27.7),(width/2,27.7)],1.0),0.65,PARED-0.15)
    total=base+carving+top_rib
    for link in links:
        total+=raised(link.offset(-0.27,circular_segments=10),0.8,PARED-0.12)
    total+=arabic_lattice(allowed,width)
    def warp(v):
        u,z,d=v
        if side=='frente':return (u,-(LARGO/2-3.3)-d,z)
        if side=='trasera':return (-u,LARGO/2-3.3+d,z)
        if side=='derecho':return (ANCHO/2-3.3+d,u,z)
        return (-ANCHO/2+3.3-d,-u,z)
    return total.warp(warp)


def mesh_of(solid):
    raw=solid.to_mesh64()
    # Keep Manifold's topology. Spatial welding can collapse distinct vertices
    # where two carved curls touch at a point and make an invalid STL edge.
    return trimesh.Trimesh(vertices=np.array(raw.vert_properties)[:,:3],
                           faces=np.array(raw.tri_verts),process=False)


def main():
    print('Construyendo mesa y canasto...',flush=True)
    # Rounded moulded table, with recessed underside and a thin top deck.
    table=ring(ANCHO-1.4,LARGO-1.4,5.5,4,1.0,28)
    table+=md.Manifold.extrude(poly(rounded_points(ANCHO,LARGO,5.8)),1.5).translate((0,0,29))
    table+=ring(ANCHO-1.2,LARGO-1.2,5.3,4,0.9,30.5)
    table+=ring(ANCHO-3.6,LARGO-3.6,4.8,3.2,0.9,31.4)
    table+=ring(79,137,5,4,2.0,30.4)
    upper=loft_shell()
    for w,l,z,h in [(75,133,32.0,1.3),(77,135,33.2,1.1),
                     (77,135,60.3,1.1),(80,138,61.4,1.2),(78.5,136.5,62.6,1.1)]:
        upper+=ring(w,l,5,2.3,h,z)
    for side in ['frente','trasera','derecho','izquierdo']:
        print('Tallando canasto:',side,flush=True)
        upper+=upper_ornament(side)
    # Four rounded corner cartouches, bound into the shell.
    for sx in [-1,1]:
        for sy in [-1,1]:
            corner=md.Manifold.sphere(1,24).scale((3.6,3.6,11.4)).translate((sx*34,sy*63,47.0))
            for z in [36.8,57.2]:
                corner+=md.Manifold.cylinder(1.3,4.1,4.1,32).translate((sx*34,sy*63,z))
            upper+=corner
    parts=[('Mesa y molduras',table,[0.67,0.57,0.40,1]),
           ('Canasto tallado',upper,[0.82,0.73,0.56,1])]
    deck=md.Manifold.extrude(poly(rounded_points(75.5,133.5,5)),1.6).translate((0,0,61.8))
    parts.append(('Tablero superior',deck,[0.71,0.61,0.44,1]))
    for side in ['frente','trasera','derecho','izquierdo']:
        print('Calando respiradero:',side,flush=True)
        parts.append(('Respiradero '+side,apron(side),[0.77,0.67,0.49,1]))
    finials=[]
    for sx in [-1,1]:
        for sy in [-1,1]:
            x,y=sx*35.2,sy*65.0
            f=md.Manifold.cylinder(1.8,2.7,2.1,32).translate((x,y,63.4))
            f+=md.Manifold.sphere(1,32).scale((2.3,2.3,3.2)).translate((x,y,67.1))
            f+=md.Manifold.cylinder(1.5,1.65,0.7,24).translate((x,y,69.0))
            finials.append(f)
    parts.append(('Cuatro remates',union(finials),[0.82,0.73,0.56,1]))

    print('Exportando y comprobando mallas...',flush=True)
    report={'unidades':'mm','fase':'Diseño completo, pendiente de revisión estética y despiece',
            'referencia':'maqueta.jfif; laterales y trasera interpretados',
            'dimensiones_objetivo':[LARGO,ANCHO],'pared_nominal_mm':PARED,
            'relieve_principal_mm':RELIEVE,'piezas_logicas':[]}
    report['celosia']={'motivo':'estrellas de ocho puntas y rombos',
                       'paso_mm':5.2,'espesor_mm':1.2,'nervios_aprox_mm':[0.9,1.0],
                       'posicion':'detrás de la talla de los cuatro respiraderos'}
    scene=trimesh.Scene()
    parts=[(name,clean_specks(solid.simplify(0.005)),color) for name,solid,color in parts]
    for name,solid,color in parts:
        mesh=mesh_of(solid)
        assert solid.status()==md.Error.NoError,(name,solid.status())
        assert mesh.is_watertight and mesh.is_winding_consistent and mesh.volume>0,(name,mesh.is_watertight,mesh.is_winding_consistent,mesh.volume)
        entry={'nombre':name,'triangulos':len(mesh.faces),
               'malla_cerrada':bool(mesh.is_watertight),'volumen_mm3':round(float(mesh.volume),2),
               'cuerpos':len(solid.decompose())}
        report['piezas_logicas'].append(entry)
        mesh.visual=trimesh.visual.ColorVisuals(mesh=mesh,vertex_colors=np.tile(np.array(color)*255,(len(mesh.vertices),1)))
        # glTF uses metres; STL and the parametric source use millimetres.
        glb_mesh=mesh.copy().apply_scale(0.001)
        scene.add_geometry(glb_mesh,node_name=name,geom_name=name)
    print('Uniendo conjunto de revisión...',flush=True)
    whole=clean_specks(union([p[1] for p in parts]))
    mesh=mesh_of(whole)
    assert mesh.is_watertight and mesh.is_winding_consistent and mesh.volume>0
    assert whole.status()==md.Error.NoError
    bodies=whole.decompose()
    # Negative-volume shells are enclosed cavities, not detached ornaments.
    positive=[c for c in bodies if c.volume()>0]
    assert len(positive)==1,[(round(c.volume(),3),c.bounding_box()) for c in positive]
    mesh.export(str(OUT/'paso_completo_revision.stl'))
    with zipfile.ZipFile(OUT/'paso_completo_revision.stl.zip','w',zipfile.ZIP_DEFLATED) as archive:
        archive.write(OUT/'paso_completo_revision.stl',arcname='paso_completo_revision.stl')
    dims=mesh.extents
    assert dims[0]<=ANCHO+0.05 and dims[1]<=LARGO+0.05, dims
    report.update({'dimensiones_reales_ancho_largo_alto_mm':np.round(dims,3).tolist(),
                   'caja_mm':np.round(mesh.bounds,3).tolist(),'triangulos_conjunto':len(mesh.faces),
                   'malla_conjunto_cerrada':bool(mesh.is_watertight),
                   'cuerpos_conjunto':len(positive),
                   'cavidades_cerradas':sum(c.volume()<0 for c in bodies),
                   'volumen_conjunto_mm3':round(float(mesh.volume),2),
                   'nota':'No se ha laminado ni comprobado físicamente. STL de revisión, no despiece de impresión.'})
    (OUT/'validacion.json').write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
    # Replace the live source only once complete; the viewer never reads half a GLB.
    tmp=OUT/'modelo_en_proceso.tmp'
    tmp.write_bytes(scene.export(file_type='glb'))
    tmp.replace(OUT/'paso_completo.glb')
    print(json.dumps({k:v for k,v in report.items() if k!='piezas_logicas'},ensure_ascii=False),flush=True)


if __name__=='__main__':
    main()

