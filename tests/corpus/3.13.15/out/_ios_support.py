import sys
try:
    from ctypes import cdll
    from ctypes import c_void_p
    from ctypes import c_char_p
    from ctypes import util
except ImportError:
    print("ctypes isn't available; iOS system calls will not be available", file=sys.stderr)
    objc = None
else:
    lib = util.find_library('objc')
    if lib is None:
        raise ImportError("ObjC runtime library couldn't be loaded")
    objc = cdll.LoadLibrary(lib)
    objc.objc_getClass.restype = c_void_p
    objc.objc_getClass.argtypes = [c_char_p]
    objc.sel_registerName.restype = c_void_p
    objc.sel_registerName.argtypes = [c_char_p]

def get_platform_ios():
    is_simulator = sys.implementation._multiarch.endswith('simulator')
    if not objc:
        return
    objc.objc_msgSend.restype = c_void_p
    objc.objc_msgSend.argtypes = [c_void_p, c_void_p]
    UIDevice = objc.objc_getClass(b'UIDevice')
    SEL_currentDevice = objc.sel_registerName(b'currentDevice')
    device = objc.objc_msgSend(UIDevice, SEL_currentDevice)
    SEL_systemVersion = objc.sel_registerName(b'systemVersion')
    device_systemVersion = objc.objc_msgSend(device, SEL_systemVersion)
    SEL_systemName = objc.sel_registerName(b'systemName')
    device_systemName = objc.objc_msgSend(device, SEL_systemName)
    SEL_model = objc.sel_registerName(b'model')
    device_model = objc.objc_msgSend(device, SEL_model)
    SEL_UTF8String = objc.sel_registerName(b'UTF8String')
    objc.objc_msgSend.restype = c_char_p
    system = objc.objc_msgSend(device_systemName, SEL_UTF8String).decode()
    release = objc.objc_msgSend(device_systemVersion, SEL_UTF8String).decode()
    model = objc.objc_msgSend(device_model, SEL_UTF8String).decode()
    return system, release, model, is_simulator

