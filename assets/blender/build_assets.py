"""Reproducible warehouse asset authoring. Run in Blender; no external assets.
In the Python console: import runpy; api = runpy.run_path(PATH); api['build_all']()
Existing scenes are preserved. Exported models have floor-centred, identity roots.
"""
import bpy
import math
import json
from pathlib import Path
from mathutils import Vector, Matrix

ROOT = Path(__file__).resolve().parents[2]
ASSET_DIR = ROOT / 'apps/frontend/public/models'
SOURCE_DIR = ROOT / 'assets/blender'
PALETTE = {}
ROOTS = {}
COLLECTIONS = {}
SCENE = None


def enum(owner, key, value):
    prop = owner.bl_rna.properties[key]
    choices = [item.identifier for item in prop.enum_items]
    if choices and value not in choices:
        raise ValueError(f'{key}: {value} not in {choices}')
    setattr(owner, key, value)


def material(name, color, metallic=0.0, roughness=.5, emission=0):
    mat = bpy.data.materials.new('SW_' + name)
    mat.use_nodes = True
    node = next(n for n in mat.node_tree.nodes if n.type == 'BSDF_PRINCIPLED')
    node.inputs['Base Color'].default_value = (*color, 1)
    node.inputs['Metallic'].default_value = metallic
    node.inputs['Roughness'].default_value = roughness
    if emission:
        node.inputs['Emission Color'].default_value = (*color, 1)
        node.inputs['Emission Strength'].default_value = emission
    mat.diffuse_color = (*color, 1)
    PALETTE[name] = mat
    return mat


def initialize():
    global SCENE
    if bpy.data.scenes.get('Warehouse · Asset Studio'):
        raise RuntimeError('Asset studio already exists; edit it instead of overwriting.')
    SCENE = bpy.data.scenes.new('Warehouse · Asset Studio')
    SCENE.render.engine = bpy.context.scene.render.engine
    bpy.context.window.scene = SCENE
    enum(SCENE.unit_settings, 'system', 'METRIC')
    SCENE.unit_settings.scale_length = 1
    material('Shell', (.64, .71, .77), .42, .31)
    material('Rubber', (.025, .037, .051), .06, .73)
    material('FleetAccent', (.035, .30, .70), .30, .3, .12)
    material('SensorGlass', (.015, .035, .055), .65, .16)
    material('RackSteel', (.10, .17, .23), .65, .38)
    material('RackBeam', (.75, .32, .075), .35, .43)
    material('Kraft', (.53, .36, .19), 0, .86)
    material('Wood', (.36, .22, .095), 0, .84)
    material('PickupBlue', (.045, .34, .75), .15, .4, .12)
    material('DropoffGreen', (.035, .48, .25), .15, .4, .12)
    material('ChargeAmber', (.95, .55, .045), .15, .4, .12)
    material('Concrete', (.58, .64, .68), .04, .87)
    material('SafetyOrange', (.95, .25, .035), .10, .49)
    material('Studio', (.72, .75, .78), 0, .9)
    print('Created asset studio and shared PBR palette; original scenes preserved.')


def asset(key, name, location):
    col = bpy.data.collections.new('SW_' + name)
    SCENE.collection.children.link(col)
    root = bpy.data.objects.new(name, None)
    col.objects.link(root)
    root.location = location
    root['asset_id'] = key
    root['author'] = 'Smart Warehouse AI · original procedural Blender model'
    root['reference_cell_metres'] = 1.0
    root['forward_axis'] = '+X'
    root['pivot'] = 'floor-centre'
    ROOTS[key], COLLECTIONS[key] = root, col
    return root


def finish(obj, root, name, mat, bevel=0, smooth=False):
    obj.name = root.name + '_' + name
    for col in list(obj.users_collection):
        col.objects.unlink(obj)
    COLLECTIONS[root['asset_id']].objects.link(obj)
    obj.parent = root
    obj.data.materials.append(PALETTE[mat])
    if bevel:
        choices = [i.identifier for i in bpy.types.Modifier.bl_rna.properties['type'].enum_items]
        assert 'BEVEL' in choices
        mod = obj.modifiers.new('Edge highlights', 'BEVEL')
        mod.width, mod.segments = bevel, 2 if root['asset_id']=='robot' else 1
    for p in obj.data.polygons:
        p.use_smooth = smooth
    return obj


def box(root, name, location, size, mat, bevel=.005):
    bpy.ops.mesh.primitive_cube_add(size=1)
    obj = bpy.context.object
    obj.data.transform(Matrix.Diagonal((*size, 1)))
    obj.location = location
    return finish(obj, root, name, mat, bevel)


def cylinder(root, name, location, radius, depth, mat, axis='Z', vertices=24, bevel=.002):
    bpy.ops.mesh.primitive_cylinder_add(vertices=vertices, radius=radius, depth=depth)
    obj = bpy.context.object
    obj.location = location
    if axis == 'Y':
        obj.rotation_euler.x = math.pi / 2
    elif axis == 'X':
        obj.rotation_euler.y = math.pi / 2
    return finish(obj, root, name, mat, bevel, True)


def beam(root, name, start, end, thickness, mat):
    a, b = Vector(start), Vector(end)
    obj = box(root, name, (a+b)/2, (thickness, thickness, (b-a).length), mat, .002)
    obj.rotation_euler = (b-a).to_track_quat('Z', 'Y').to_euler()
    return obj


def flat_polygon(root, name, xy, z, mat):
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata([(x, y, z) for x, y in xy], [], [tuple(range(len(xy)))])
    obj = bpy.data.objects.new(name, mesh)
    COLLECTIONS[root['asset_id']].objects.link(obj)
    return finish(obj, root, name, mat)


def carton(root, name, location, size):
    box(root, name, location, size, 'Kraft', .006)
    x, y, z = location
    sx, sy, sz = size
    box(root, name+'_Strap', (x, y, z+sz/2+.001), (sx+.002, .018, .002), 'RackBeam' if root['asset_id']=='shelf' else 'Wood', 0)
    box(root, name+'_Label', (x, y-sy/2-.001, z+.02), (sx*.36, .002, sz*.25), 'RackSteel' if root['asset_id']=='shelf' else 'Shell', 0)


def make_robot():
    r = asset('robot', 'AMR', (-1.8, -1.3, 0))
    box(r, 'Chassis', (0,0,.145), (.69,.47,.15), 'Rubber', .026)
    box(r, 'Body', (0,0,.238), (.74,.53,.135), 'Shell', .035)
    box(r, 'DeckGasket', (0,0,.31), (.63,.49,.024), 'Rubber', .009)
    box(r, 'Deck', (0,0,.336), (.61,.48,.028), 'Shell', .012)
    for sign in [-1,1]:
        box(r, 'SideAccent', (0,sign*.269,.245), (.57,.013,.055), 'FleetAccent', .006)
        box(r, 'RearBumper', (-.37,sign*.155,.16), (.04,.21,.065), 'Rubber', .012)
        box(r, 'FrontLight', (.369,sign*.175,.27), (.017,.09,.018), 'FleetAccent', .004)
        for x in [-.22,.22]:
            label = ('F' if x>0 else 'R') + ('L' if sign>0 else 'R')
            cylinder(r, 'Wheel_'+label+'_Tire', (x, sign*.25,.085), .085,.07,'Rubber','Y',24,.004)
            cylinder(r, 'Wheel_'+label+'_Hub', (x, sign*.283,.085), .046,.008,'Shell','Y',20,.002)
            cylinder(r, 'Wheel_'+label+'_Axle', (x, sign*.2875,.085), .018,.005,'SensorGlass','Y',12,.001)
    box(r, 'SensorFascia', (.371,0,.195), (.023,.27,.085), 'Rubber', .01)
    for y in [-.078,.078]:
        cylinder(r, 'OpticalSensor', (.386,y,.2), .024,.006,'SensorGlass','X',20,.001)
    cylinder(r, 'LidarBase', (-.285,0,.357), .037,.014,'Rubber', vertices=24)
    cylinder(r, 'LidarLens', (-.285,0,.371), .034,.014,'SensorGlass', vertices=24)
    cylinder(r, 'StatusLight', (-.285,0,.378), .027,.004,'FleetAccent', vertices=24,bevel=.001)
    for y in [-.14,.14]:
        for i in range(4):
            box(r, 'Vent', (-.255+i*.026,y,.309), (.013,.08,.002), 'Rubber', .001)
    return r


def make_shelf():
    r = asset('shelf','Shelf',(-1.8,1.0,0))
    for x in [-.42,.42]:
        for y in [-.42,.42]:
            box(r,'Foot',(x,y,.015),(.08,.08,.03),'RackSteel',.003)
            box(r,'Upright',(x,y,.835),(.035,.035,1.63),'RackSteel',.003)
    for level in [.14,.82,1.5]:
        box(r,'ShelfDeck',(0,0,level),(.84,.84,.025),'RackSteel',.003)
        for y in [-.432,.432]:
            box(r,'Beam',(0,y,level-.025),(.9,.045,.065),'RackBeam',.003)
    for y in [-.42,.42]:
        box(r,'TopTie',(0,y,1.61),(.86,.025,.025),'RackSteel',.002)
    beam(r,'RearBraceA',(-.4,.44,.17),(.4,.44,.79),.016,'RackSteel')
    beam(r,'RearBraceB',(.4,.44,.17),(-.4,.44,.79),.016,'RackSteel')
    for i,(x,y,z,size) in enumerate([(-.22,0,.38,(.34,.58,.45)),(.19,.06,.34,(.35,.46,.37)),(-.21,.04,1.055,(.34,.48,.44)),(.20,.035,1.11,(.32,.55,.55))]):
        carton(r,'Carton'+str(i),(x,y,z),size)
    return r


def make_station(kind):
    is_charge = kind=='charger'
    name = {'pickup':'Pickup','dropoff':'Dropoff','charger':'Charger'}[kind]
    position = {'pickup':(0,1,0),'dropoff':(1.8,1,0),'charger':(0,-1.3,0)}[kind]
    accent = {'pickup':'PickupBlue','dropoff':'DropoffGreen','charger':'ChargeAmber'}[kind]
    r = asset(kind,name,position)
    box(r,'FloorPad',(0,0,.002),(.92,.92,.004),'Rubber',.018)
    for y in [-.432,.432]:
        box(r,'LaneMark',(0,y,.005),(.84,.015,.002),accent,0)
    for x in [-.432,.432]:
        box(r,'EndMark',(x,0,.005),(.015,.84,.002),accent,0)
    if not is_charge:
        box(r,'TerminalFoot',(-.427,.31,.025),(.065,.18,.05),'Shell',.006)
        box(r,'TerminalMast',(-.427,.31,.33),(.055,.075,.59),'Shell',.005)
        box(r,'TerminalHead',(-.427,.31,.685),(.065,.22,.21),'Shell',.008)
        box(r,'Screen',(-.391,.31,.7),(.004,.164,.115),'SensorGlass',.002)
        box(r,'Signal',(-.427,.31,.794),(.045,.16,.012),accent,.003)
        for y in [.255,.295,.335]:
            box(r,'ScreenIndicator',(-.387,y,.705),(.002,.022,.034),accent,0)
        direction = 1 if kind=='pickup' else -1
        for x in [-.18,.12]:
            points=[(x-.10,-.055),(x+.015,-.055),(x+.015,-.105),(x+.13,0),(x+.015,.105),(x+.015,.055),(x-.10,.055)]
            if direction<0: points=[(-a,b) for a,b in reversed(points)]
            flat_polygon(r,'Direction',points,.0055,accent)
    else:
        box(r,'DockBase',(-.43,0,.035),(.06,.66,.07),'Shell',.008)
        box(r,'DockBody',(-.43,0,.255),(.06,.59,.44),'Shell',.01)
        box(r,'DockTop',(-.43,0,.51),(.06,.59,.08),'ChargeAmber',.01)
        box(r,'DockPanel',(-.396,0,.29),(.004,.36,.17),'SensorGlass',.003)
        for y in [-.17,.17]:
            box(r,'ChargingContact',(-.394,y,.105),(.008,.065,.06),'ChargeAmber',.005)
        flat_polygon(r,'Lightning',[(-.04,.19),(.12,.19),(.02,.025),(.14,.025),(-.1,-.2),(-.04,-.035),(-.16,-.035)],.0055,accent)
    return r


def make_pallet():
    r=asset('pallet','Pallet',(1.8,-1.3,0))
    for x in [-.21,0,.21]:
        box(r,'Runner',(x,0,.02),(.08,.48,.04),'Wood',.003)
    for y in [-.195,-.0975,0,.0975,.195]:
        box(r,'Slat',(0,y,.065),(.55,.075,.05),'Wood',.003)
    carton(r,'CargoLeft',(-.13,0,.2),(.24,.42,.22))
    carton(r,'CargoRight',(.13,0,.2),(.24,.42,.22))
    return r


def make_wall():
    r=asset('wall','Wall',(3.6,1,0))
    box(r,'Panel',(0,0,.8),(1,1,1.6),'Concrete',.018)
    for y in [-.496,.496]:
        box(r,'Skirting',(0,y,.065),(.94,.008,.13),'RackSteel',.002)
    return r


def make_obstacle():
    r=asset('obstacle','Obstacle',(3.6,-1.3,0))
    for x in [-.29,.29]:
        box(r,'Foot',(x,0,.035),(.2,.8,.07),'Rubber',.012)
        box(r,'Post',(x,0,.31),(.075,.075,.55),'SafetyOrange',.008)
    box(r,'Barrier',(0,0,.43),(.8,.1,.2),'SafetyOrange',.015)
    for x in [-.24,0,.24]:
        box(r,'Reflector',(x,-.052,.43),(.1,.004,.14),'Shell',.001)
        box(r,'Reflector',(x,.052,.43),(.1,.004,.14),'Shell',.001)
    return r


def bounds(root):
    bpy.context.view_layer.update()
    graph=bpy.context.evaluated_depsgraph_get()
    inv=root.matrix_world.inverted()
    points=[inv @ ob.evaluated_get(graph).matrix_world @ Vector(corner) for ob in root.children_recursive if ob.type=='MESH' for corner in ob.evaluated_get(graph).bound_box]
    lo=[min(p[i] for p in points) for i in range(3)]
    hi=[max(p[i] for p in points) for i in range(3)]
    return {'min':[round(v,5) for v in lo], 'max':[round(v,5) for v in hi], 'size':[round(hi[i]-lo[i],5) for i in range(3)]}


def studio():
    col=bpy.data.collections.new('SW_StudioLighting')
    SCENE.collection.children.link(col)
    def link(obj): col.objects.link(obj); return obj
    floor=bpy.data.meshes.new('StudioFloor')
    floor.from_pydata([(-5,-4,-.012),(7,-4,-.012),(7,5,-.012),(-5,5,-.012)],[],[(0,1,2,3)])
    floor.materials.append(PALETTE['Studio'])
    link(bpy.data.objects.new('SW_StudioFloor',floor))
    for name,loc,power,size in [('Key',(0,-3,7),1100,6),('Fill',(-4,1,4),750,5),('Rim',(3,4,6),1000,4)]:
        light_type=next(i.identifier for i in bpy.types.Light.bl_rna.properties['type'].enum_items if i.identifier=='AREA')
        light=bpy.data.lights.new('SW_'+name,type=light_type)
        light.energy,light.size=power,size
        enum(light,'shape','DISK')
        obj=link(bpy.data.objects.new('SW_'+name,light));obj.location=loc
        obj.rotation_euler=(Vector((.8,0,.4))-obj.location).to_track_quat('-Z','Y').to_euler()
    world=bpy.data.worlds.new('SW_StudioWorld');world.use_nodes=True
    bg=next(n for n in world.node_tree.nodes if n.type=='BACKGROUND')
    bg.inputs[0].default_value=(.7,.76,.85,1); bg.inputs[1].default_value=.35
    SCENE.world=world
    data=bpy.data.cameras.new('SW_Camera');enum(data,'type','ORTHO');data.ortho_scale=8.8
    cam=link(bpy.data.objects.new('SW_Camera',data));cam.location=(6,-9,7)
    cam.rotation_euler=(Vector((.8,0,.45))-cam.location).to_track_quat('-Z','Y').to_euler()
    SCENE.camera=cam
    SCENE.render.resolution_x=1400;SCENE.render.resolution_y=1000;SCENE.render.resolution_percentage=100
    for screen in bpy.data.screens:
        for area in screen.areas:
            if area.type=='VIEW_3D':
                area.spaces.active.region_3d.view_location=(.7,0,.5)
                area.spaces.active.region_3d.view_distance=8
                area.spaces.active.region_3d.view_rotation=cam.rotation_euler.to_quaternion()
                area.spaces.active.overlay.show_overlays=False
                enum(area.spaces.active.shading,'type','MATERIAL')
    print('Studio camera, floor and soft lighting ready.')


def export_asset(key):
    root=ROOTS[key]
    source_scene=bpy.context.window.scene
    graph=bpy.context.evaluated_depsgraph_get()
    inv=root.matrix_world.inverted()
    temp=bpy.data.scenes.new('SW_Export_'+key)
    export_root=bpy.data.objects.new(root.name+'_Export',None)
    export_root.name=root.name+'_Root'
    temp.collection.objects.link(export_root)
    for k,v in root.items():export_root[k]=v
    groups={}
    for ob in root.children_recursive:
        if ob.type!='MESH': continue
        evaluated=ob.evaluated_get(graph)
        mesh=bpy.data.meshes.new_from_object(evaluated,depsgraph=graph)
        mesh.transform(inv @ ob.matrix_world)
        copy=bpy.data.objects.new(ob.name+'_Export',mesh)
        temp.collection.objects.link(copy)
        copy.parent=export_root
        group='Body' if key=='robot' else root.name+'_Geometry'
        if key=='robot' and '_Wheel_' in ob.name:
            group='Wheel_'+ob.name.split('_Wheel_')[1].split('_')[0]
        groups.setdefault(group,[]).append(copy)
    bpy.context.window.scene=temp
    for name,objects in groups.items():
        bpy.ops.object.select_all(action='DESELECT')
        for ob in objects:ob.select_set(True)
        bpy.context.view_layer.objects.active=objects[0]
        bpy.ops.object.join()
        merged=bpy.context.object;merged.name=name
        if name.startswith('Wheel_'):
            coords=[v.co for v in merged.data.vertices]
            centre=Vector([(min(v[i] for v in coords)+max(v[i] for v in coords))/2 for i in range(3)])
            merged.data.transform(Matrix.Translation(-centre));merged.location=centre
    bpy.ops.object.select_all(action='SELECT')
    relative='robots/amr.glb' if key=='robot' else 'warehouse/'+key+'.glb'
    path=ASSET_DIR/relative;path.parent.mkdir(parents=True,exist_ok=True)
    rna=bpy.ops.export_scene.gltf.get_rna_type()
    import io_scene_gltf2
    fmt=next(item[0] for item in io_scene_gltf2.get_format_items(SCENE,bpy.context) if item[0]=='GLB')
    bpy.ops.export_scene.gltf(filepath=str(path),export_format=fmt,use_selection=True,use_active_scene=True,export_yup=True,export_apply=False,export_animations=False,export_cameras=False,export_lights=False,export_extras=True,export_materials='EXPORT',export_draco_mesh_compression_enable=False)
    export_objects=list(temp.objects)
    bpy.context.window.scene=source_scene
    bpy.data.scenes.remove(temp)
    for ob in export_objects:
        mesh=ob.data if ob.type=='MESH' else None
        bpy.data.objects.remove(ob,do_unlink=True)
        if mesh and not mesh.users:bpy.data.meshes.remove(mesh)
    print(key, bounds(root), path.stat().st_size, 'bytes')
    return str(path)


def save_source():
    SOURCE_DIR.mkdir(parents=True,exist_ok=True)
    path=SOURCE_DIR/'warehouse-assets.blend'
    bpy.ops.wm.save_as_mainfile(filepath=str(path))
    print('Saved editable source:', path)


def build_all():
    initialize(); make_robot(); make_shelf()
    for kind in ('pickup','dropoff','charger'):make_station(kind)
    make_pallet();make_wall();make_obstacle();studio()
    for key in ROOTS:export_asset(key)
    save_source()


def resume():
    """Rebind authoring handles in a new Blender console / MCP execution namespace."""
    global SCENE, PALETTE, ROOTS, COLLECTIONS
    SCENE = bpy.data.scenes['Warehouse · Asset Studio']
    bpy.context.window.scene = SCENE
    ROOTS = {ob['asset_id']: ob for ob in SCENE.objects if 'asset_id' in ob and ob.parent is None}
    COLLECTIONS = {key: root.users_collection[0] for key, root in ROOTS.items()}
    PALETTE = {mat.name.removeprefix('SW_'): mat for mat in bpy.data.materials if mat.name.startswith('SW_')}


def verify_exports():
    """Import optimized GLBs into isolated scenes and compare their physical bounds."""
    resume()
    reports = []
    for key, source in ROOTS.items():
        expected = bounds(source)
        temp = bpy.data.scenes.new('SW_Validation_' + key)
        bpy.context.window.scene = temp
        try:
            relative = 'robots/amr.glb' if key == 'robot' else 'warehouse/' + key + '.glb'
            bpy.ops.import_scene.gltf(filepath=str(ASSET_DIR / relative))
            roots = [ob for ob in temp.objects if ob.parent is None]
            assert len(roots) == 1, f'{key}: expected one root'
            actual = bounds(roots[0])
            for edge in ('min', 'max'):
                assert all(abs(a-b) < .0001 for a, b in zip(actual[edge], expected[edge])), f'{key}: bounds changed'
            reports.append({'asset': key, 'bounds_metres_blender_xyz': actual, 'roundtrip': 'passed'})
        finally:
            objects = list(temp.objects)
            bpy.context.window.scene = SCENE
            bpy.data.scenes.remove(temp)
            for ob in objects:
                mesh = ob.data if ob.type == 'MESH' else None
                bpy.data.objects.remove(ob, do_unlink=True)
                if mesh and not mesh.users:
                    bpy.data.meshes.remove(mesh)
    (SOURCE_DIR / 'blender-bounds.json').write_text(json.dumps(reports, indent=2) + '\n')
    print('All 8 optimized GLBs match source bounds within 0.1 mm.')
