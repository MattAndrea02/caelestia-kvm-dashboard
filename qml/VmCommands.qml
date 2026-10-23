pragma Singleton

import QtQuick
import Quickshell
import qs.utils

Singleton {
    function python(script: string, args: var): var {
        return ["python3", "-B", Paths.toLocalFile(Qt.resolvedUrl(script)), ...(args || [])];
    }
}
