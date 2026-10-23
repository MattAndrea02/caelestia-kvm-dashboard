.pragma library

function memory(kib) {
    if (kib === null || kib === undefined)
        return "Unavailable";
    return kib >= 1048576 ? (kib / 1048576).toFixed(1) + " GiB" : (kib / 1024).toFixed(0) + " MiB";
}
