// Elements by id
els = {};

window.addEventListener('load', (event) => {
    for (let e of document.querySelectorAll('[id]')) {
        els[e.id] = e;
    }

    on_gps_change()
    els.gps_ok.addEventListener('change', on_gps_change);
    els.sel_dev_gps.addEventListener('change', on_gps_change);

    on_usbl_change()
    els.usbl_ok.addEventListener('change', on_usbl_change);
    els.sel_dev_usbl.addEventListener('change', on_usbl_change);

    on_mav_change()
    els.mav_ok.addEventListener('change', on_mav_change);
    els.input_mav.addEventListener('change', on_mav_change);

    on_echo_change()
    els.echo_ok.addEventListener('change', on_echo_change);
    els.input_echo.addEventListener('change', on_echo_change);
});

eel.expose(on_list_usb_devices);
eel.expose(add_to_log);
eel.expose(on_controller_attr_changed);

function on_controller_attr_changed(key, value) {
    switch (key) {
        case 'dev_usbl':
            if (value) {
                els.sel_dev_usbl.value = value;
            }
            els.usbl_ok.checked = !!value;

            break;
        case 'dev_gps':
            if (value) {
                els.sel_dev_gps.value = value;
            }
            els.gps_ok.checked = !!value;
            break;
        case 'addr_mav':
            if (value) {
                els.input_mav.value = value;
            }
            els.mav_ok.checked = !!value;
            break;
        case 'addr_echo':
            if (value) {
                els.input_echo.value = value;
            }
            els.echo_ok.checked = !!value;
    }
}

function on_gps_change() {
    els.gps_ok.disabled = !els.sel_dev_gps.value;

    let dev = null;
    if (els.gps_ok.checked) {
        dev = els.sel_dev_gps.value || null;
    }
    eel.controller_set_attr('dev_gps', dev)();
}

function on_usbl_change() {
    els.usbl_ok.disabled = !els.sel_dev_usbl.value;

    let dev = null;
    if (els.usbl_ok.checked) {
        dev = els.sel_dev_usbl.value || null;
    }
    eel.controller_set_attr('dev_usbl', dev)();
}

function on_echo_change() {
    els.echo_ok.disabled = !els.input_echo.value;

    let addr = null;
    if (els.echo_ok.checked) {
        addr = els.input_echo.value || null;
    }
    eel.controller_set_attr('addr_echo', addr)();
}

function on_mav_change() {
    els.mav_ok.disabled = !els.input_mav.value;

    let addr = null;
    if (els.mav_ok.checked) {
        addr = els.input_mav.value || null;
    }
    eel.controller_set_attr('addr_mav', addr)();
}


function add_to_log(contents) {
    let li = document.createElement('li');
    li.innerText = contents;
    document.getElementById('event_log').appendChild(li);
}

function on_list_usb_devices(devices) {
    let sel_dev_usbl = document.getElementById('sel_dev_usbl');
    let sel_dev_gps = document.getElementById('sel_dev_gps');

    for (let sel of [sel_dev_usbl, sel_dev_gps]) {
        let value = sel.value;
        for (let i = sel.options.length - 1; i >= 1; i--) {
            sel.options.remove(i)
        }
        for (let device of devices) {
            let opt = document.createElement('option');
            opt.appendChild(document.createTextNode(device));
            opt.value = device;
            sel.appendChild(opt)
        }
        sel.value = value;
    }
}

