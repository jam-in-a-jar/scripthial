import platform
import math
from ctypes import *
nt = windll.ntdll
k32 = windll.kernel32
u32 = windll.user32
#
# ekknod@2019
#


bone_list = [5, 4, 3, 0, 7, 8]
head_only = False
aim_smooth = 5
aim_fov = 1.0 / 180.0
aim_key = 107       # mouse 1
trigger_key = 111   # mouse5
quit_key = 72       # insert


class Vector3(Structure):
    _fields_ = [('x', c_float), ('y', c_float), ('z', c_float)]


def array_to_data(address):
    r = 0
    for j in bytearray(reversed(address)):
        r = (r << 8) + j
    return r


class ProcessList:
    def __init__(self):
        length = c_uint()
        self.snap = create_string_buffer(8)
        nt.NtQuerySystemInformation(57, self.snap, 0x188, pointer(length))
        self.snap = create_string_buffer(length.value + 8192)
        if nt.NtQuerySystemInformation(57, self.snap, length.value + 8192, 0) != 0:
            raise Exception("[!]ProcessList::__init__")
        self.pos = 0

    def next(self):
        temp = array_to_data(self.snap[self.pos:self.pos + 4])
        if temp != 0:
            self.pos = temp + self.pos
            return True
        return False

    def pid(self):
        return int(array_to_data(self.snap[self.pos + 0x128:self.pos + 0x130]))

    def wow64(self):
        return array_to_data(self.snap[self.pos + 0x160:self.pos + 0x168]) <= 0xffffffff

    def teb(self):
        return c_int64(array_to_data(self.snap[self.pos + 0x168:self.pos + 0x170])).value

    def name(self):
        name = create_unicode_buffer(120)
        nt.memcpy(name, c_int64(array_to_data(self.snap[self.pos + 0x40:self.pos + 0x48])), 120)
        return name.value


class Process:
    def __init__(self, name):
        temp = c_uint8()
        nt.RtlAdjustPrivilege(20, 1, 0, pointer(temp))
        temp = ProcessList()
        status = False
        while temp.next():
            temp_handle = k32.OpenProcess(0x410, 0, temp.pid())
            if temp.name() == name:
                self.mem = temp_handle
                self.wow64 = temp.wow64()
                if self.wow64:
                    self.peb = self.read_i64(temp.teb() + 0x2030, 4)
                else:
                    self.peb = self.read_i64(temp.teb() + 0x0060, 8)
                status = True
                # break
        if not status:
            raise Exception("[!]Process is not running!")

    def is_running(self):
        buffer = c_uint32()
        k32.GetExitCodeProcess(self.mem, pointer(buffer))
        return buffer.value == 0x103

    def read_vec3(self, address):
        buffer = Vector3()
        nt.NtReadVirtualMemory(self.mem, c_long(address), pointer(buffer), 12, 0)
        return buffer

    def read_string(self, address, length=120):
        buffer = create_string_buffer(length)
        nt.NtReadVirtualMemory(self.mem, address, buffer, length, 0)
        return buffer.value

    def read_unicode(self, address, length=120):
        buffer = create_unicode_buffer(length)
        nt.NtReadVirtualMemory(self.mem, address, pointer(buffer), length, 0)
        return buffer.value

    def read_float(self, address, length=4):
        buffer = c_float()
        nt.NtReadVirtualMemory(self.mem, c_long(address), pointer(buffer), length, 0)
        return buffer.value

    def read_i8(self, address, length=1):
        buffer = c_uint8()
        nt.NtReadVirtualMemory(self.mem, address, pointer(buffer), length, 0)
        return buffer.value

    def read_i16(self, address, length=2):
        buffer = c_uint16()
        nt.NtReadVirtualMemory(self.mem, address, pointer(buffer), length, 0)
        return buffer.value

    def read_i32(self, address, length=4):
        buffer = c_uint32()
        nt.NtReadVirtualMemory(self.mem, address, pointer(buffer), length, 0)
        return buffer.value

    def read_i64(self, address, length=8):
        buffer = c_uint64()
        nt.NtReadVirtualMemory(self.mem, c_uint64(address), pointer(buffer), length, 0)
        return buffer.value

    def write_i16(self, address, value):
        buffer = c_uint16(value)
        return nt.NtWriteVirtualMemory(self.mem, address, pointer(buffer), 2, 0) == 0

    def write_i64(self, address, value):
        buffer = c_uint64(value)
        return nt.NtWriteVirtualMemory(self.mem, address, pointer(buffer), 8, 0) == 0

    def get_module(self, name):
        if self.wow64:
            a0 = [0x04, 0x0C, 0x14, 0x28, 0x10]
        else:
            a0 = [0x08, 0x18, 0x20, 0x50, 0x20]
        a1 = self.read_i64(self.read_i64(self.peb + a0[1], a0[0]) + a0[2], a0[0])
        a2 = self.read_i64(a1 + a0[0], a0[0])
        while a1 != a2:
            val = self.read_unicode(self.read_i64(a1 + a0[3], a0[0]))
            if str(val).lower() == name.lower():
                return self.read_i64(a1 + a0[4], a0[0])
            a1 = self.read_i64(a1, a0[0])
        raise Exception("[!]Process::get_module")

    def get_export(self, module, name):
        if module == 0:
            return 0
        a0 = self.read_i32(module + self.read_i16(module + 0x3C) + (0x88 - self.wow64 * 0x10)) + module
        a1 = [self.read_i32(a0 + 0x18), self.read_i32(a0 + 0x1c), self.read_i32(a0 + 0x20), self.read_i32(a0 + 0x24)]
        while a1[0] > 0:
            a1[0] -= 1
            export_name = self.read_string(module + self.read_i32(module + a1[2] + (a1[0] * 4)), 120)
            if name.encode('ascii', 'ignore') == export_name:
                a2 = self.read_i16(module + a1[3] + (a1[0] * 2))
                a3 = self.read_i32(module + a1[1] + (a2 * 4))
                return module + a3
        raise Exception("[!]Process::get_export")


class VirtualTable:
    def __init__(self, table):
        self.table = table

    def function(self, index):
        return mem.read_i32(mem.read_i32(self.table) + index * 4)


class InterfaceTable:
    def __init__(self, name):
        self.table_list = mem.read_i32(mem.read_i32(mem.get_export(mem.get_module(name), 'CreateInterface') - 0x6A))

    def get_interface(self, name):
        a0 = self.table_list
        while a0 != 0:
            if name.encode('ascii', 'ignore') == mem.read_string(mem.read_i32(a0 + 0x4), 120)[0:-3]:
                return VirtualTable(mem.read_i32(mem.read_i32(a0) + 1))
            a0 = mem.read_i32(a0 + 0x8)
        raise Exception('[!]InterfaceTable::get_interface')


class NetVarTable:
    def __init__(self, name):
        self.table = 0
        a0 = mem.read_i32(mem.read_i32(vt.client.function(8) + 1))
        while a0 != 0:
            a1 = mem.read_i32(a0 + 0x0C)
            if name.encode('ascii', 'ignore') == mem.read_string(mem.read_i32(a1 + 0x0C), 120):
                self.table = a1
            a0 = mem.read_i32(a0 + 0x10)
        if self.table == 0:
            raise Exception('[!]NetVarTable::__init__')

    def get_offset(self, name):
        offset = self.__get_offset(self.table, name)
        if offset == 0:
            raise Exception('[!]NetVarTable::get_offset')
        return offset

    def __get_offset(self, address, name):
        a0 = 0
        for a1 in range(0, mem.read_i32(address + 0x4)):
            a2 = a1 * 60 + mem.read_i32(address)
            a3 = mem.read_i32(a2 + 0x2C)
            a4 = mem.read_i32(a2 + 0x28)
            if a4 != 0 and mem.read_i32(a4 + 0x4) != 0:
                a5 = self.__get_offset(a4, name)
                if a5 != 0:
                    a0 += a3 + a5
            if name.encode('ascii', 'ignore') == mem.read_string(mem.read_i32(a2), 120):
                return a3 + a0
        return a0


class ConVar:
    def __init__(self, name):
        self.address = 0
        a0 = mem.read_i32(mem.read_i32(mem.read_i32(vt.cvar.table + 0x34)) + 0x4)
        while a0 != 0:
            if name.encode('ascii', 'ignore') == mem.read_string(mem.read_i32(a0 + 0x0C)):
                self.address = a0
                break
            a0 = mem.read_i32(a0 + 0x4)
        if self.address == 0:
            raise Exception('[!]ConVar not found!')

    def get_int(self):
        a0 = c_int32()
        a1 = mem.read_i32(self.address + 0x30) ^ self.address
        nt.memcpy(pointer(a0), pointer(c_int32(a1)), 4)
        return a0.value

    def get_float(self):
        a0 = c_float()
        a1 = mem.read_i32(self.address + 0x2C) ^ self.address
        nt.memcpy(pointer(a0), pointer(c_int32(a1)), 4)
        return a0.value


class InterfaceList:
    def __init__(self):
        table = InterfaceTable('client_panorama.dll')
        self.client = table.get_interface('VClient')
        self.entity = table.get_interface('VClientEntityList')
        table = InterfaceTable('engine.dll')
        self.engine = table.get_interface('VEngineClient')
        table = InterfaceTable('vstdlib.dll')
        self.cvar = table.get_interface('VEngineCvar')
        table = InterfaceTable('inputsystem.dll')
        self.input = table.get_interface('InputSystemVersion')


class NetVarList:
    def __init__(self):
        table = NetVarTable('DT_BasePlayer')
        self.m_iHealth = table.get_offset('m_iHealth')
        self.m_vecViewOffset = table.get_offset('m_vecViewOffset[0]')
        self.m_lifeState = table.get_offset('m_lifeState')
        self.m_nTickBase = table.get_offset('m_nTickBase')
        self.m_vecPunch = table.get_offset('m_Local') + 0x70

        table = NetVarTable('DT_BaseEntity')
        self.m_iTeamNum = table.get_offset('m_iTeamNum')
        self.m_vecOrigin = table.get_offset('m_vecOrigin')

        table = NetVarTable('DT_CSPlayer')
        self.m_hActiveWeapon = table.get_offset('m_hActiveWeapon')
        self.m_iShotsFired = table.get_offset('m_iShotsFired')
        self.m_iCrossHairID = table.get_offset('m_bHasDefuser') + 0x5C
        self.m_iGlowIndex = table.get_offset('m_flFlashDuration') + 0x18

        table = NetVarTable('DT_BaseAnimating')
        self.m_dwBoneMatrix = table.get_offset('m_nForceBone') + 0x1C

        table = NetVarTable('DT_BaseAttributableItem')
        self.m_iItemDefinitionIndex = table.get_offset('m_iItemDefinitionIndex')

        self.dwEntityList = vt.entity.table - (mem.read_i32(vt.entity.function(5) + 0x22) - 0x38)
        self.dwClientState = mem.read_i32(mem.read_i32(vt.engine.function(18) + 0x16))
        self.dwGetLocalPlayer = mem.read_i32(vt.engine.function(12) + 0x16)
        self.dwViewAngles = mem.read_i32(vt.engine.function(19) + 0xB2)
        self.dwMaxClients = mem.read_i32(vt.engine.function(20) + 0x07)
        self.dwState = mem.read_i32(vt.engine.function(26) + 0x07)
        self.dwButton = mem.read_i32(vt.input.function(15) + 0x21D)


class Player:
    def __init__(self, address):
        self.address = address

    def get_team_num(self):
        return mem.read_i32(self.address + nv.m_iTeamNum)

    def get_health(self):
        return mem.read_i32(self.address + nv.m_iHealth)

    def get_life_state(self):
        return mem.read_i32(self.address + nv.m_lifeState)

    def get_tick_count(self):
        return mem.read_i32(self.address + nv.m_nTickBase)

    def get_shots_fired(self):
        return mem.read_i32(self.address + nv.m_iShotsFired)

    def get_cross_index(self):
        return mem.read_i32(self.address + nv.m_iCrossHairID)

    def get_weapon(self):
        a0 = mem.read_i32(self.address + nv.m_hActiveWeapon)
        return mem.read_i32(nv.dwEntityList + ((a0 & 0xFFF) - 1) * 0x10)

    def get_weapon_id(self):
        return mem.read_i32(self.get_weapon() + nv.m_iItemDefinitionIndex)

    def get_origin(self):
        return mem.read_vec3(self.address + nv.m_vecOrigin)

    def get_vec_view(self):
        return mem.read_vec3(self.address + nv.m_vecViewOffset)

    def get_eye_pos(self):
        v = self.get_vec_view()
        o = self.get_origin()
        return Vector3(v.x + o.x, v.y + o.y, v.z + o.z)

    def get_vec_punch(self):
        return mem.read_vec3(self.address + nv.m_vecPunch)

    def get_bone_pos(self, index):
        a0 = 0x30 * index
        a1 = mem.read_i32(self.address + nv.m_dwBoneMatrix)
        return Vector3(
            mem.read_float(a1 + a0 + 0x0C),
            mem.read_float(a1 + a0 + 0x1C),
            mem.read_float(a1 + a0 + 0x2C)
        )

    def is_valid(self):
        health = self.get_health()
        return self.address != 0 and self.get_life_state() == 0 and 0 < health < 1338


class Engine:
    @staticmethod
    def get_local_player():
        return mem.read_i32(nv.dwClientState + nv.dwGetLocalPlayer)

    @staticmethod
    def get_view_angles():
        return mem.read_vec3(nv.dwClientState + nv.dwViewAngles)

    @staticmethod
    def get_max_clients():
        return mem.read_i32(nv.dwClientState + nv.dwMaxClients)

    @staticmethod
    def is_in_game():
        return mem.read_i8(nv.dwClientState + nv.dwState) >> 2


class Entity:
    @staticmethod
    def get_client_entity(index):
        return Player(mem.read_i32(nv.dwEntityList + index * 0x10))


class InputSystem:
    @staticmethod
    def is_button_down(button):
        a0 = mem.read_i32(vt.input.table + ((button >> 5) * 4) + nv.dwButton)
        return (a0 >> (button & 31)) & 1


class Math:
    @staticmethod
    def sin_cos(radians):
        return [math.sin(radians), math.cos(radians)]

    @staticmethod
    def rad2deg(x):
        return x * 3.141592654

    @staticmethod
    def deg2rad(x):
        return x * 0.017453293

    @staticmethod
    def angle_vec(angles):
        s = Math.sin_cos(Math.deg2rad(angles.x))
        y = Math.sin_cos(Math.deg2rad(angles.y))
        return Vector3(s[1] * y[1], s[1] * y[0], -s[0])

    @staticmethod
    def vec_normalize(vec):
        radius = 1.0 / (math.sqrt(vec.x * vec.x + vec.y * vec.y + vec.z * vec.z) + 1.192092896e-07)
        vec.x *= radius
        vec.y *= radius
        vec.z *= radius
        return vec

    @staticmethod
    def vec_angles(forward):
        if forward.y == 0.00 and forward.x == 0.00:
            yaw = 0
            pitch = 270.0 if forward.z > 0.00 else 90.0
        else:
            yaw = math.atan2(forward.y, forward.x) * 57.295779513
            if yaw < 0.00:
                yaw += 360.0
            tmp = math.sqrt(forward.x * forward.x + forward.y * forward.y)
            pitch = math.atan2(-forward.z, tmp) * 57.295779513
            if pitch < 0.00:
                pitch += 360.0
        return Vector3(pitch, yaw, 0.00)

    @staticmethod
    def vec_clamp(v):
        if 89.0 < v.x <= 180.0:
            v.x = 89.0
        if v.x > 180.0:
            v.x -= 360.0
        if v.x < -89.0:
            v.x = -89.0
        v.y = math.fmod(v.y + 180.0, 360.0) - 180.0
        v.z = 0.00
        return v

    @staticmethod
    def vec_dot(v0, v1):
        return v0.x * v1.x + v0.y * v1.y + v0.z * v1.z

    @staticmethod
    def vec_length(v):
        return v.x * v.x + v.y * v.y + v.z * v.z

    @staticmethod
    def get_fov(va, angle):
        a0 = Math.angle_vec(va)
        a1 = Math.angle_vec(angle)
        return Math.rad2deg(math.acos(Math.vec_dot(a0, a1) / Math.vec_length(a0)))


def get_target_angle(local_p, target, bone_id):
    m = target.get_bone_pos(bone_id)
    c = local_p.get_eye_pos()
    c.x = m.x - c.x
    c.y = m.y - c.y
    c.z = m.z - c.z
    c = Math.vec_angles(Math.vec_normalize(c))
    if local_p.get_shots_fired() > 1:
        p = local_p.get_vec_punch()
        c.x -= p.x * 2.0
        c.y -= p.y * 2.0
        c.z -= p.z * 2.0
    return Math.vec_clamp(c)


_target = Player(0)
_target_bone = 0


def get_best_target(va, local_p):
    global _target
    global _target_bone
    a0 = 9999.9
    for i in range(1, Engine.get_max_clients()):
        entity = Entity.get_client_entity(i)
        if not entity.is_valid():
            continue
        if not mp_teammates_are_enemies.get_int() and local_p.get_team_num() == entity.get_team_num():
            continue
        if head_only:
            fov = Math.get_fov(va, get_target_angle(local_p, entity, 8))
            if fov < a0:
                a0 = fov
                _target = entity
                _target_bone = 8
        else:
            for j in range(0, bone_list.__len__()):
                fov = Math.get_fov(va, get_target_angle(local_p, entity, bone_list[j]))
                if fov < a0:
                    a0 = fov
                    _target = entity
                    _target_bone = bone_list[j]
    return a0 != 9999


_current_tick = 0
_previous_tick = 0


def aim_at_target(va, angle):
    global _current_tick
    global _previous_tick
    y = va.x - angle.x
    x = va.y - angle.y
    if y > 89.0:
        y = 89.0
    elif y < -89.0:
        y = -89.0
    if x > 180.0:
        x -= 360.0
    elif x < -180.0:
        x += 360.0
    if math.fabs(x) / 180.0 >= aim_fov:
        return
    if math.fabs(y) / 89.0 >= aim_fov:
        return
    fl_sensitivity = sensitivity.get_float()
    x = (x / fl_sensitivity) / 0.022
    y = (y / fl_sensitivity) / -0.022
    if aim_smooth != 0.00:
        sx = 0.00
        sy = 0.00
        if sx < x:
            sx += 1.0 + (x / aim_smooth)
        elif sx > x:
            sx -= 1.0 - (x / aim_smooth)
        if sy < y:
            sy += 1.0 + (y / aim_smooth)
        elif sy > y:
            sy -= 1.0 - (y / aim_smooth)
    else:
        sx = x
        sy = y
    if _current_tick - _previous_tick > 0:
        _previous_tick = _current_tick
        u32.mouse_event(0x0001, int(sx), int(sy), 0, 0)


if __name__ == "__main__":
    if platform.architecture()[0] != '64bit':
        print('[!]64bit python required')
        exit(0)
    try:
        mem = Process('csgo.exe')
        vt = InterfaceList()
        nv = NetVarList()
        sensitivity = ConVar('sensitivity')
        mp_teammates_are_enemies = ConVar('mp_teammates_are_enemies')
    except Exception as e:
        print(e)
        exit(0)

    print('[*]VirtualTables')
    print('    VClient:            ' + hex(vt.client.table))
    print('    VClientEntityList:  ' + hex(vt.entity.table))
    print('    VEngineClient:      ' + hex(vt.engine.table))
    print('    VEngineCvar:        ' + hex(vt.cvar.table))
    print('    InputSystemVersion: ' + hex(vt.input.table))
    print('[*]Offsets')
    print('    EntityList:         ' + hex(nv.dwEntityList))
    print('    ClientState:        ' + hex(nv.dwClientState))
    print('    GetLocalPlayer:     ' + hex(nv.dwGetLocalPlayer))
    print('    GetViewAngles:      ' + hex(nv.dwViewAngles))
    print('    GetMaxClients:      ' + hex(nv.dwMaxClients))
    print('    IsInGame:           ' + hex(nv.dwState))
    print('[*]NetVars')
    print('    m_iHealth:          ' + hex(nv.m_iHealth))
    print('    m_vecViewOffset:    ' + hex(nv.m_vecViewOffset))
    print('    m_lifeState:        ' + hex(nv.m_lifeState))
    print('    m_nTickBase:        ' + hex(nv.m_nTickBase))
    print('    m_vecPunch:         ' + hex(nv.m_vecPunch))
    print('    m_iTeamNum:         ' + hex(nv.m_iTeamNum))
    print('    m_vecOrigin:        ' + hex(nv.m_vecOrigin))
    print('    m_hActiveWeapon:    ' + hex(nv.m_hActiveWeapon))
    print('    m_iShotsFired:      ' + hex(nv.m_iShotsFired))
    print('    m_iCrossHairID:     ' + hex(nv.m_iCrossHairID))
    print('    m_dwBoneMatrix:     ' + hex(nv.m_dwBoneMatrix))
    print('[*]Info')
    print('    Creator:            github.com/ekknod')
    previous_tick = 0
    while mem.is_running() and not InputSystem.is_button_down(quit_key):
        k32.Sleep(1)
        if Engine.is_in_game():
            if Engine.is_in_game():
                try:
                    self = Entity.get_client_entity(Engine.get_local_player())
                    weapon_id = self.get_weapon_id()
                    if weapon_id == 42 or weapon_id == 49:
                        continue
                    if InputSystem.is_button_down(trigger_key):
                        cross_id = self.get_cross_index()
                        if cross_id == 0:
                            continue
                        cross_target = Entity.get_client_entity(cross_id - 1)
                        if self.get_team_num() != cross_target.get_team_num() and cross_target.get_health() > 0:
                            u32.mouse_event(0x0002, 0, 0, 0, 0)
                            u32.mouse_event(0x0004, 0, 0, 0, 0)
                    if InputSystem.is_button_down(aim_key):
                        view_angle = Engine.get_view_angles()
                        _current_tick = self.get_tick_count()
                        if not _target.is_valid() and not get_best_target(view_angle, self):
                            continue
                        aim_at_target(view_angle, get_target_angle(self, _target, _target_bone))
                    else:
                        _target = Player(0)
                except ValueError:
                    continue