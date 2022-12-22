# ==============================================================================
#  Copyright (c) 2022 Thomas Mathieson.
# ==============================================================================

import time

import bpy
import os
import bmesh
from . import o3d_cfg_parser, o3dconvert

if not (bpy.app.version[0] < 3 and bpy.app.version[1] < 80):
    from bpy_extras import node_shader_utils

# from . import log


def log(*args):
    print("[O3D_Export]", *args)


def export_mesh(filepath, context, mesh, materials):
    # Create o3d file
    with open(filepath, "wb") as f:
        has_uvs = len(mesh.uv_layers) > 0
        if has_uvs:
            uv_layer = mesh.uv_layers.active.data[:]

        # Extract mesh data
        tris = []
        verts = []
        vert_map = {}
        vert_id = 0
        """
        for face in mesh.faces:
            tri = []
            tris.append(tri)

            for loop in face.loops:
                v = loop.vert

                uv = loop[uv_layer].uv[:2]

                normal = v.normal
                # normal = [-n for n in normal]
                normal = (0, 1, 0)

                # log(normal)

                verts.append((-v.co[0], v.co[1], v.co[2],
                              normal[0], normal[1], normal[2],
                              uv[0], 1 - uv[1]))
                vert_map[uv] = vert_id
                tri.append(vert_id)
                vert_id += 1

            # Triangle material ID
            tri.append(face.material_index)
        """

        face_index_pairs = [(face, index) for index, face in enumerate(mesh.polygons)]
        no_key = no_val = None
        normals_to_idx = {}
        no_get = normals_to_idx.get
        loops_to_normals = [0] * len(loops)
        for f, f_index in face_index_pairs:
            for l_idx in f.loop_indices:
                no_key = veckey3d(loops[l_idx].normal)
                no_val = no_get(no_key)
                if no_val is None:
                    no_val = normals_to_idx[no_key] = no_unique_count
                    fw('vn %.4f %.4f %.4f\n' % no_key)
                    no_unique_count += 1
                loops_to_normals[l_idx] = no_val
        del normals_to_idx, no_get, no_key, no_val

        for v in mesh.vertices:
            verts.append((*v.co, ))

        o3d_mats = []
        for mat in materials:
            # O3D mat structure:
            # (diffuse_r, diffuse_g, diffuse_b, diffuse_a, specular_r, specular_g, specular_b, emission_r, emission_g,
            #  emission_b, specular_power, texture_name)
            o3d_mat = []
            o3d_mats.append(o3d_mat)
            if bpy.app.version[0] < 3 and bpy.app.version[1] < 80:
                mat = mat.material
                o3d_mat.extend(mat.diffuse_color)
                o3d_mat.extend(mat.alpha)
                o3d_mat.extend(mat.specular_color)
                o3d_mat.extend(mat.emission_color)
                o3d_mat.append(mat.specular_hardness)
                # TODO: Blender 2.79 compat for texture export in embedded materials
                # o3d_mat.append(os.path.basename(mat.base_color_texture.image.filepath))
            else:
                mat = node_shader_utils.PrincipledBSDFWrapper(mat.material, is_readonly=True)
                o3d_mat.extend(mat.base_color)
                o3d_mat.append(mat.alpha)
                o3d_mat.extend([mat.specular, mat.specular, mat.specular])
                o3d_mat.extend(mat.emission_color)
                o3d_mat.append(1 - mat.roughness)
                o3d_mat.append(os.path.basename(mat.base_color_texture.image.filepath))

        o3dconvert.export_o3d(f, verts, tris, o3d_mats, [], None,
                              version=1,
                              encrypted=False, encryption_key=0xffffffff,
                              long_triangle_indices=False,
                              alt_encryption_seed=True)


def do_export(filepath, context, global_matrix, use_selection):
    """
    Exports the selected CFG/SCO/O3D file
    :param use_selection: export only the selected objects
    :param global_matrix: transformation matrix to apply before export
    :param filepath: the path to the file to import
    :param context: blender context
    :return: success message
    """
    obj_root = os.path.dirname(filepath)
    start_time = time.time()

    if bpy.ops.object.mode_set.poll():
        bpy.ops.object.mode_set(mode='OBJECT')

    if use_selection:
        obs = context.selected_objects
    else:
        obs = context.scene.objects

    deps_graph = context.evaluated_depsgraph_get()

    bpy.context.window_manager.progress_begin(0, len(obs))

    single_o3d = False
    if filepath[-3:] == "o3d":
        single_o3d = True
        cfg_materials = {}
    else:
        cfg_materials = o3d_cfg_parser.merge_cfg(filepath, obs)

    index = 0
    for ob in obs:
        log("Exporting " + ob.name + "...")
        bpy.context.window_manager.progress_update(index)
        ob_eval = ob.evaluated_get(deps_graph)

        try:
            me = ob_eval.to_mesh()
        except RuntimeError:
            continue

        me.transform(ob.matrix_world)
        bm = bmesh.new()
        bm.from_mesh(me)

        if global_matrix is not None:
            bm.transform(global_matrix)

        if bpy.app.version[0] < 3 and bpy.app.version[1] < 80:
            bmesh.ops.triangulate(bm, faces=bm.faces[:], quad_method=0, ngon_method=0)
        else:
            bmesh.ops.triangulate(bm, faces=bm.faces)

        bm.to_mesh(me)
        bm.free()

        me.calc_normals_split()

        # Export individual model
        path = os.path.join(obj_root, ob.name + ".o3d")
        if single_o3d:
            if len(obs) == 1:
                path = filepath
            else:
                path = os.path.join(obj_root, os.path.basename(filepath)[:-4] + "-" + ob.name + ".o3d")
        export_mesh(path, context, me, ob_eval.material_slots)

        index += 1

    bpy.context.window_manager.progress_end()
    log("Exported {0} models in {1} seconds!".format(len(obs), time.time() - start_time))