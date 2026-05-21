#!/usr/bin/python3
import sys, struct, wrapper, threading, time
from wrapper import recv_from_any_link, send_to_link, get_switch_mac, get_interface_name

TPID_POLI   = 0x8200
NATIVE_VLAN = 1   # VLAN nativ (ne-tagged) pe trunk

# configurarea VLAN-ului
port_mode = {}      # access sau trunk
access_vlan = {}    # base VID (doar pe portul de access)

# Functia citeste configuratia switch-uli din folderul configs
# seteaza porturile ca acces/trunk + VLAN urile corespunzatoare
def load_switch_cfg(switch_id, num_ifaces):
    cfg_path = f"configs/switch{switch_id}.cfg"
    try:
        with open(cfg_path, "r") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"): continue
                t = line.split()
                if t[0].lower() == "access":
                    i, vid = int(t[1]), int(t[2])
                    port_mode[i]  = "access"
                    access_vlan[i]= vid
                elif t[0].lower() == "trunk":
                    i = int(t[1])
                    port_mode[i] = "trunk"
    except FileNotFoundError:
        # daca nu exista configuratie, default toate porturile
        # devin acces VLAN 1
        for i in range(num_ifaces):
            port_mode[i]  = "access"
            access_vlan[i]= 1
    # completam porturile care nu au fost configurate explicit
    for i in range(num_ifaces):
        if i not in port_mode:
            port_mode[i] = "access"
        if port_mode[i] == "access" and i not in access_vlan:
            access_vlan[i] = 1

# functii auxiliare
# calculeaza suma nibble-urilor din MAC (folosit pentru EXT ID)
def sum_mac_nibbles(mac_bytes: bytes) -> int:
    # practic ia fiecare byte si aduna cele doua jumatati
    s = 0
    for b in mac_bytes:
        s += (b >> 4) + (b & 0xF)
    return s & 0xF # EXT ID ramane pe 4 biti

# verifica daca frame-ul are tag POLI
# tagul POLI este identificat prin TPID = 0x8200 la byte 12-13
def are_poli_tag(data: bytes) -> bool:
    return len(data) >= 16 and ((data[12] << 8) + data[13]) == TPID_POLI

# adauga tag POLI in frame (folosit pentru trunk sau VLAN != nativ)
# TCI = 12 biti pentru VID + 4 biti pentru EXT ID
def adauga_poli_tag(frame: bytes, base_vid: int, ext_id: int) -> bytes:
    tci = ((ext_id & 0xF) << 12) | (base_vid & 0x0FFF)
    return frame[0:12] + struct.pack("!HH", TPID_POLI, tci) + frame[12:]

#elimina tag POLI din frame (scoatem cei 4 byti ai tagului POLI)
def eliminate_poli_tag(frame: bytes) -> bytes:
    return frame[0:12] + frame[16:]

# extrage informatiile VLAN din frame
def get_tag_info(frame: bytes):
    if not are_poli_tag(frame):
        return (False, -1, -1)
    # extragem TCI-ul pentru VLAN ID si EXT ID
    tci = int.from_bytes(frame[14:16], "big")
    return (True, tci & 0x0FFF, (tci >> 12) & 0xF)

# parseaza header-ul Ethernet si detecteaza VLAN daca exista
def parseaza_ethernet_header(data):
    dest_mac = data[0:6]
    src_mac  = data[6:12]
    ether_type = (data[12] << 8) + data[13]
    vlan_id = -1
    vlan_tci = -1
    if ether_type == TPID_POLI:
        vlan_tci = int.from_bytes(data[14:16], "big")
        vlan_id  = vlan_tci & 0x0FFF
        ether_type = (data[16] << 8) + data[17]
    return dest_mac, src_mac, ether_type, vlan_id, vlan_tci

def function_on_different_thread():
    while True:
        time.sleep(1)

# verifica daca MAC este unicast
def is_unicast_mac_bytes(mac_b: bytes) -> bool:
    return (mac_b[0] & 0x01) == 0

def main():
    switch_id = sys.argv[1]
    mac_table = {}

    num_interfaces = wrapper.init(sys.argv[2:])
    interfaces = range(0, num_interfaces)
    load_switch_cfg(switch_id, num_interfaces)

    print(f"# Starting switch with id {switch_id}", flush=True)
    print("[INFO] Switch MAC", ':'.join(f'{b:02x}' for b in get_switch_mac()))
    threading.Thread(target=function_on_different_thread, daemon=True).start()
    for i in interfaces:
        print(get_interface_name(i))

    # helper pentru egress: verifica extensia la unicast pe ACCESS pentru cand e cu tag si cand e untagged
    # trunk: VLAN 1 nativ (untagged), altfel este tagged; extensia e pusa din sursa pentru unicast
    def forward_to_port(out_if, frame, base_vid, src_ext, src_mac_bytes, dest_mac_bytes, is_unicast):
        if port_mode[out_if] == "trunk":
            if base_vid == NATIVE_VLAN:
                # VLAN pe ac switch(nativ): trimitem fara tag
                if are_poli_tag(frame):
                    frame = eliminate_poli_tag(frame)
                send_to_link(out_if, len(frame), frame)
            else:
                # VLAN nenativ: trimitem cu tag (sau scot tag-ul)
                if are_poli_tag(frame):
                    _, tag_vid, _ = get_tag_info(frame)
                    if tag_vid != base_vid:
                        frame = eliminate_poli_tag(frame)
                        frame = adauga_poli_tag(frame, base_vid, src_ext if is_unicast else 0)
                else:
                    frame = adauga_poli_tag(frame, base_vid, src_ext if is_unicast else 0)
                send_to_link(out_if, len(frame), frame)
            return

        # ACCESS: mereu UNTAGGED
        #izolez pe VLAN si o sa impun EXT la unicast
        if are_poli_tag(frame):
            _, tag_vid, tag_ext = get_tag_info(frame)
            if tag_vid != access_vlan[out_if]:
                return
            if is_unicast:
                # la tagged+unicast, ext trebuie sa corespunda SURSA (hostul care a pus tagul)
                src_ext_from_frame = sum_mac_nibbles(src_mac_bytes)
                if tag_ext != src_ext_from_frame:
                    return
            frame = eliminate_poli_tag(frame)
        else:
            if base_vid != access_vlan[out_if]:
                return
            if is_unicast:
                # la untagged+unicast, ext-ul „logic” al cadrului (src_ext din ingress)
                # trebuie sa se potriveasca cu ext-ul destinatiei
                dest_ext = sum_mac_nibbles(dest_mac_bytes)
                if src_ext != dest_ext:
                    return
        send_to_link(out_if, len(frame), frame)

    # bucla de comutare
    while True:
        interface, data, length = recv_from_any_link()


        if get_interface_name(interface) == 'rr-0-2':
            continue

        dest_mac_bytes, src_mac_bytes, _, _, _ = parseaza_ethernet_header(data)
        dest_mac_str = ':'.join(f'{b:02x}' for b in dest_mac_bytes).lower()
        src_mac_str  = ':'.join(f'{b:02x}' for b in src_mac_bytes).lower()

        ing_tagged, in_vid, in_ext = get_tag_info(data)
        if port_mode[interface] == "access":
            base_vid = access_vlan[interface]
            src_ext  = sum_mac_nibbles(src_mac_bytes)
        else:
            # trunk: acceptam tagged; fara tag: VLAN nativ
            if ing_tagged:
                base_vid = in_vid
                src_ext  = in_ext
            else:
                base_vid = NATIVE_VLAN
                src_ext  = sum_mac_nibbles(src_mac_bytes)

        # learning (MAC, VLAN)
        mac_table[(src_mac_str, base_vid)] = (interface, time.time(), src_ext)

        # Tabela MAC
        is_unicast = is_unicast_mac_bytes(dest_mac_bytes)
        dst_key    = (dest_mac_str, base_vid)

        if is_unicast:
            entry = mac_table.get(dst_key)
            if entry is not None:
                out_if, _, _ = entry
                if out_if != interface:
                    forward_to_port(out_if, data, base_vid, src_ext, src_mac_bytes, dest_mac_bytes, True)
            else:
                # unknown unicast: flood doar in VLAN; ext-ul se valideaza la egress pe port ACCESS
                for i in interfaces:
                    if i == interface:
                        continue
                    if port_mode[i] == "access" and access_vlan[i] != base_vid:
                        continue
                    forward_to_port(i, data, base_vid, src_ext, src_mac_bytes, dest_mac_bytes, True)
        else:
            # broadcast: flood este doar in acelasi VLAN(ext ignorat)
            for i in interfaces:
                if i == interface:
                    continue
                if port_mode[i] == "access" and access_vlan[i] != base_vid:
                    continue
                forward_to_port(i, data, base_vid, src_ext, src_mac_bytes, dest_mac_bytes, False)

        # TODO: Implement STP support

if __name__ == "__main__":
    main()
    