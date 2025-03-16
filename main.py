#! /usr/bin/python
# -*- coding: utf-8 -*-

guitarix_pgm = "guitarix -p 7000"

import socket, json, os, time, serial, json

class RpcNotification:

    def __init__(self, method, params):
        self.method = method
        self.params = params


class RpcResult:

    def __init__(self, id, result):
        self.id = id
        self.result = result


class RpcSocket:

    def __init__(self, address=("localhost",7000)):
        self.s = socket.socket()
        self.s.connect(address)
        self.buf = b""
        self.banks = []
        self.presets = []

    def send(self, method, id=None, params=[]):
        d = dict(jsonrpc="2.0", method=method, params=params)
        if id is not None:
            d["id"] ="1"
        json_dump_w_nl = json.dumps(d) + "\n"
        jdump_as_bytes = str.encode(json_dump_w_nl)
        self.s.send(jdump_as_bytes)

    def call(self, method, params=[]):
        self.send(method=method, id="1", params=params)

    def notify(self, method, params=[]):
        self.send(method=method, params=params)

    def receive(self):
        while True:
            if b"\n" in self.buf:
                ln, sep, tail = self.buf.partition(b'\n')  # Split at newline
                self.buf = tail  # Save remaining buffer
                st = ln.decode("utf-8")  # Decode bytes to string
                break
            self.buf += self.s.recv(10000)  # Append received bytes

        try:
            d = json.loads(st)
        except ValueError as e:
            print (e)
            print (st)
            return None
        if "params" in d:
            if not d["params"]:
                return None
            elif not  ".v" in (d["params"][0]):
                print(d["params"])
            return RpcNotification(d["method"], d["params"])
        elif "result" in d:
            return RpcResult(d["id"], d["result"])
        else:
            raise ValueError("rpc error: %s" % d)

    def check_parameter(self):
        while self:
            rpc = self.receive()
            if rpc == None:
                break
            elif isinstance(rpc, RpcNotification):
                print(rpc.params, end=" ", flush=True)

    def print_current_preset(self):
        time.sleep(0.01)
        # print out current bank and preset
        self.call("get", ["system.current_bank"])
        bank = self.receive().result["system.current_bank"]
        self.call("get", ["system.current_preset"])
        preset = self.receive().result["system.current_preset"]
        print("\n\n" + '\033[95mBANK: ' + bank +" PRESET: " + preset + "\033[0m" + "\n")

    def get_current_preset(self):
        time.sleep(0.01)
        # print out current bank and preset
        self.call("get", ["system.current_bank"])
        bank = self.receive().result["system.current_bank"]
        self.call("get", ["system.current_preset"])
        preset = self.receive().result["system.current_preset"]
        #print("\n\n" + '\033[95mBANK: ' + bank +" PRESET: " + preset + "\033[0m" + "\n")
        return bank, preset

    def get_banks(self):
        self.call("banks",[])
        r = self.receive().result
        for  d in r:
            self.banks.append(d['name'])
            self.presets.append(d['presets'])


class Guitarix():

    def open_socket(self):
        try:
            self.sock = RpcSocket()
        except socket.error as e:
            if e.errno != 111:
                raise
            return False
        return True

    def __init__(self):
        self.current_params = {}
        if not self.open_socket():
            
            os.system(guitarix_pgm+"&")
            for i in range(10):
                time.sleep(1)
                if self.open_socket():
                    break
            else:
                raise RuntimeError("Can't connect to Guitarix")
            self

def refresh_paramlist(sock):
    sock.call("parameterlist", [])
    parameterlist = []
    r = sock.receive().result
    for tp, d in zip(r[::2], r[1::2]):
        if tp == "Enum":
            d = d["IntParameter"]
        elif tp == "FloatEnum":
            d = d["FloatParameter"]
        d = d["Parameter"]
        n = d["id"]
        if "non_preset" in d and n not in ("system.current_preset", "system.current_bank"):
            continue
        parameterlist.append(d["id"])
    parameterlist.sort()

def init_serial():
    ser = serial.Serial(
        port='/dev/ttyUSB0',
        baudrate=115200,
        parity=serial.PARITY_NONE,
        stopbits=serial.STOPBITS_ONE,
        bytesize=serial.EIGHTBITS,
        timeout=1
    )
    return ser

def read_serial(ser):
    while True:
        read = ser.readline()
        decoded_str = read.decode()
        if len(decoded_str) != 0 and decoded_str[0] == '{':
            data = json.loads(read)
            #print(data)
            return data
            #time.sleep(1)


def main():
    print("starting ctrlpdl host")
    #start guitarix with rpc port at 7000
    gx = Guitarix()
    print ("started guitarix")
    # open a socket at 7000
    sock = RpcSocket()
    # receive all available parameters from guitarix
    sock.call("parameterlist", [])
    parameterlist = []
    r = sock.receive().result
    for tp, d in zip(r[::2], r[1::2]):
        if tp == "Enum":
            d = d["IntParameter"]
        elif tp == "FloatEnum":
            d = d["FloatParameter"]
        d = d["Parameter"]
        n = d["id"]
        if "non_preset" in d and n not in ("system.current_preset", "system.current_bank"):
            continue
        parameterlist.append(d["id"])
    parameterlist.sort()
    # print out parameterlist
    for i in parameterlist:
        print(i)
    
    # get current value of a parameter
    sock.call("get", ['wah.freq'])
    print(sock.receive().result)
    # set new value for a parameter
    sock.notify("set", ['wah.freq', 50])
    while True:
        try:
            ser = init_serial()
        except:
            print("uh oh, no serial device found on the specified port, retrying...")
        else:
            break

    sock.get_banks()
    sock.print_current_preset()
    next_bank = 0
    sock.notify("setpreset", [sock.banks[next_bank], sock.presets[next_bank][0]])
    next_bank = next_bank + 1
    # and now listen to all parameter changes 
    #sock.notify("listen",['all'])

    with open('presets.json') as presets_file:
        presets_data = json.load(presets_file)
        curr_effects_arr = []
        
        while sock:
            #print("loopdeloop")
            preset_tuple = sock.get_current_preset()
            #print(preset_tuple)
            if preset_tuple[0] not in presets_data["banks"]:
                curr_effects_arr = presets_data["default"]["switches"]
            elif preset_tuple[0] not in presets_data["banks"][preset_tuple[0]]:
                curr_effects_arr = presets_data["default"]["switches"]
                #do default
            else:
                curr_effects_arr = presets_data["banks"][preset_tuple[0]][preset_tuple[1]]["switches"]

            #print(curr_effects_arr)
                

            
            json_data = read_serial(ser)
            for i in range(0, len(curr_effects_arr)):
                data_tmp = json_data["pedals"][i]
                #print("eff: " + curr_effects_arr[i] + " val: " + str(data_tmp))
                sock.notify("set", [curr_effects_arr[i], data_tmp])

            if json_data["ui_action"] == "nxbk":
                sock.notify("setpreset", [sock.banks[next_bank], sock.presets[next_bank][0]])
                next_bank = next_bank + 1
                if next_bank > len(sock.banks):
                    next_bank = 0
            elif json_data["ui_action"] == "pxbk":
                next_bank = next_bank - 2
                if next_bank < 0:
                    next_bank = len(sock.banks)-1
                sock.notify("setpreset", [sock.banks[next_bank], sock.presets[next_bank][0]])
                next_bank = next_bank + 1
                if next_bank > len(sock.banks):
                    next_bank = 0
            elif json_data["ui_action"] == "nxps":
                sock.notify("set", ['engine.next_preset',1])
            elif json_data["ui_action"] == "pxps":
                sock.notify("set", ['engine.previus_preset',1])
            #print(type(json_data["pedals"][0]))
            #print(json_data["pedals"][0])
            #refresh_paramlist(sock)
            #print("before")
            #if sock.receive() == None:
            #    print("Error: sock.receive is nonw")
            #    break
            #print("after")

    print("you could say I'm... out of the loop :p")

if __name__=="__main__":
    main()
