# Copyright 2010 Hardcoded Software (http://www.hardcoded.net)

# This software is licensed under the "BSD" License as described in the "LICENSE" file,
# which should be included with this package. The terms are also available at
# http://www.hardcoded.net/licenses/bsd_license

from ctypes import cdll, byref, Structure, c_char, c_char_p
from ctypes.util import find_library

Foundation = cdll.LoadLibrary(find_library('Foundation'))
CoreServices = cdll.LoadLibrary(find_library('CoreServices'))

GetMacOSStatusCommentString = Foundation.GetMacOSStatusCommentString
GetMacOSStatusCommentString.restype = c_char_p
FSPathMakeRefWithOptions = CoreServices.FSPathMakeRefWithOptions
FSMoveObjectToTrashSync = CoreServices.FSMoveObjectToTrashSync

kFSPathMakeRefDefaultOptions = 0
kFSPathMakeRefDoNotFollowLeafSymlink = 0x01

kFSFileOperationDefaultOptions = 0
kFSFileOperationOverwrite = 0x01
kFSFileOperationSkipSourcePermissionErrors = 0x02
kFSFileOperationDoNotMoveAcrossVolumes = 0x04
kFSFileOperationSkipPreflight = 0x08

class FSRef(Structure):
    _fields_ = [('hidden', c_char * 80)]

def check_op_result(op_result):
    if op_result:
        msg = GetMacOSStatusCommentString(op_result).decode('utf-8')
        raise OSError(msg)

def send2trash(path):
    if not isinstance(path, bytes):
        path = path.encode('utf-8')
    fp = FSRef()
    opts = kFSPathMakeRefDoNotFollowLeafSymlink
    op_result = FSPathMakeRefWithOptions(path, opts, byref(fp), None)
    check_op_result(op_result)
    opts = kFSFileOperationDefaultOptions
    op_result = FSMoveObjectToTrashSync(byref(fp), None, opts)
    check_op_result(op_result)
