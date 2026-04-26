var pseudo_popup = function (config) {
	var _int_event_add = function (object, name, handler) {
		if ('addEventListener' in object) {
			object.addEventListener (name, handler, false);
		} else if ('attachEvent' in object) {
			object.attachEvent ('on' + name, handler);
		} else {
			object ['on' + name] = handler;
		}
	};

	var _int_event_remove = function (object, name, handler) {
		if ('removeEventListener' in object) {
			object.removeEventListener (name, handler, false);
		} else if ('detachEvent' in object) {
			object.detachEvent ('on' + name, handler);
		} else {
			object ['on' + name] = '';
		}
	};

	var _int_event_prevent_default = function (event) {
		if ('preventDefault' in event) {
			event.preventDefault ();
		} else if ('returnValue' in event) {
			event.returnValue = false;
		}
	};

	var _int_create_dom = function () {
		var _int_create_element = function (element_name, class_name) {
			var dom_div;

			dom_div = document.createElement (element_name);
			if (class_name) {
				dom_div.className = class_name;
			}
			return (dom_div);
		};

		var _int_create_div = function (class_name) {
			return (_int_create_element ('div', class_name));
		};

		_dat_dom_main = _int_create_div ('pseudo_popup');
		_dat_dom_top = _int_create_div ('');
		_dat_dom_top.appendChild (_int_create_div ('top_left'));
		_dat_dom_top_middle = _dat_dom_top.appendChild (_int_create_div ('top_middle'));
		_dat_dom_top_right = _dat_dom_top.appendChild (_int_create_div ('top_right'));
		_dat_dom_close = _dat_dom_top_right.appendChild (_int_create_div ('close'));
		_int_event_add (_dat_dom_close, 'click', _int_destroy);
		_dat_dom_main.appendChild (_dat_dom_top);
		_dat_dom_content = _dat_dom_main.appendChild (_int_create_div ('content'));
		_dat_dom_iframe = _dat_dom_content.appendChild (_int_create_element ('iframe'));
		_dat_dom_iframe.frameBorder = '0';
		_int_event_add (_dat_dom_iframe, 'load', _int_iframe_onload);
		_dat_dom_main.appendChild (_int_create_div ('bottom_left'));
		_dat_dom_bottom_middle = _dat_dom_main.appendChild (_int_create_div ('bottom_middle'));
		_dat_dom_main.appendChild (_int_create_div ('bottom_right'));
		_dat_dom_main.appendChild (_int_create_div ('clear'));
		document.body.appendChild (_dat_dom_main);
	};

	var _int_drag_prepare = function () {
		var delta_horiz, delta_vert;

		_int_event_add (_dat_dom_top, 'mousedown', _int_drag_start);
		_int_event_add (_dat_dom_top, 'dragstart', _int_drag_ignore);
	};

	var _int_drag_start = function (event) {
		var scroll;

		if (event === undefined) {
			event = window.event;
		}
		_dat_dragging = true;
		scroll = _int_get_scroll ();
		delta_horiz = _dat_pos_left - (event.clientX + scroll.left);
		delta_vert = _dat_pos_top - (event.clientY + scroll.top);
		_int_event_add (document, 'mousemove', _int_drag_move_main);
		_int_event_add (document, 'mouseup', _int_drag_stop);
		_int_iframe_listen ();
		_int_event_prevent_default (event);	/* NB: Prevent builtin item dragging on Firefox */
	};

	var _int_drag_ignore = function (event) {
		if (event === undefined) {
			event = window.event;
		}
		_int_event_prevent_default (event);	/* NB: Prevent builtin item dragging on IE */
	};

	var _int_drag_move_main = function (event) {
		var scroll;

		if (event === undefined) {
			event = window.event;
		}
		scroll = _int_get_scroll ();
		_dat_this.set_left (event.clientX + scroll.left + delta_horiz);
		_dat_this.set_top (event.clientY + scroll.top + delta_vert);
	};

	var _int_drag_move_iframe = function (event) {
		var scroll;

		if (event === undefined) {
			event = window.event;
		}
		scroll = _int_get_scroll ();
		_dat_this.set_left (_dat_pos_left + _dat_iframe_offset_left + event.clientX + delta_horiz);
		_dat_this.set_top (_dat_pos_top + _dat_iframe_offset_top + event.clientY + delta_vert);
	};

	var _int_drag_stop = function (event) {
		if (event === undefined) {
			event = window.event;
		}
		_int_event_remove (document, 'mousemove', _int_drag_move_main);
		_int_event_remove (document, 'mouseup', _int_drag_stop);
		if (_dat_dom_iframe.contentWindow) {
			_int_event_remove (_dat_dom_iframe.contentWindow.document, 'mousemove', _int_drag_move_iframe);
			_int_event_remove (_dat_dom_iframe.contentWindow.document, 'mouseup', _int_drag_stop);
		}
		_dat_dragging = false;
	};

	var _int_iframe_onload = function () {
		_int_iframe_listen ();
		_int_fire ('load');
	};

	var _int_iframe_listen = function () {
		if (_dat_dragging && _dat_dom_iframe.contentWindow) {
			_int_event_add (_dat_dom_iframe.contentWindow.document, 'mousemove', _int_drag_move_iframe);
			_int_event_add (_dat_dom_iframe.contentWindow.document, 'mouseup', _int_drag_stop);
		}
	};

	var _int_get_scroll = function () {
		if (
			(document.documentElement.scrollTop != 0) ||
			(document.documentElement.scrollLeft != 0)
		) {
			return ({
				left: document.documentElement.scrollLeft,
				top: document.documentElement.scrollTop
			});
		}
		if (
			(document.body.scrollTop != 0) ||
			(document.body.scrollLeft != 0)
		) {
			return ({
				left: document.body.scrollLeft,
				top: document.body.scrollTop
			});
		}
		return ({left: 0, top: 0});
	};

	var _int_destroy = function () {
		_int_fire ('destroy');
		_int_event_remove (_dat_dom_iframe, 'load', _int_iframe_onload);
		_int_event_remove (_dat_dom_top_right, 'click', _int_destroy);
		_int_event_remove (_dat_dom_top, 'mousedown', _int_drag_start);
		_int_event_remove (_dat_dom_top, 'dragstart', _int_drag_ignore);
		document.body.removeChild (_dat_dom_main);
		_dat_this = null;
		_dat_callback = null;
		_dat_dragging = null;
		_dat_dom_main = null;
		_dat_dom_top = null;
		_dat_dom_top_middle = null;
		_dat_dom_top_right = null;
		_dat_dom_content = null;
		_dat_dom_iframe = null;
		_dat_dom_bottom_middle = null;
		_dat_dom_close = null;
		_dat_size_width = null;
		_dat_pos_left = null;
		_dat_pos_top = null;
	};

	var _int_fire = function (name) {
		if (_dat_callback !== null) {
			_dat_callback (name);
		}
	};

	var _dat_this;
	var _dat_callback;
	var _dat_dragging;
	var _dat_dom_main;
	var _dat_dom_top;
	var _dat_dom_top_middle;
	var _dat_dom_top_right;
	var _dat_dom_content;
	var _dat_dom_iframe;
	var _dat_dom_bottom_middle;
	var _dat_dom_close;
	var _dat_size_width;
	var _dat_pos_left;
	var _dat_pos_top;
	var _dat_iframe_offset_left = 1;
	var _dat_iframe_offset_top = 23;
	var _dat_reserve_width = 100;
	var _dat_bar_height = 22;

	this.set_left = function (value) {
		var min_left, max_left;

		min_left = _dat_reserve_width - _dat_size_width;
		max_left = screen.availWidth - _dat_reserve_width;
		if (value < min_left) {
			value = min_left;
		} else if (value > max_left) {
			value = max_left;
		}
		_dat_dom_main.style.left = value + 'px';
		_dat_pos_left = value;
	};
	this.set_top = function (value) {
		var max_top;

		max_top = screen.availHeight - _dat_bar_height - 140;
		if (value < 0) {
			value = 0;
		} else if (value > max_top) {
			value = max_top;
		}
		_dat_dom_main.style.top = value + 'px';
		_dat_pos_top = value;
	};
	this.set_width = function (value) {
		_dat_dom_main.style.width = value + 'px';
		_dat_dom_top_middle.style.width = (value - 8 - 58) + 'px';
		_dat_dom_bottom_middle.style.width = (value - 9 - 9) + 'px';
		_dat_size_width = value;
	};
	this.set_height = function (value) {
		_dat_dom_main.style.height = value + 'px';
		_dat_dom_content.style.height = (value - 22 - 9 - 1) + 'px';
	};
	this.get_iframe = function () {
		return (_dat_dom_iframe);
	};
	this.navigate = function (url) {
		_dat_dom_iframe.src = url;
	};
	this.destroy = function () {
		_int_destroy ();
	};

	var scroll;

	_dat_this = this;
	_dat_callback = ('callback' in config) ? config.callback : null;
	_dat_dragging = false;
	_int_create_dom ();
	_int_drag_prepare ();
	scroll = _int_get_scroll ();
	this.set_left ((('left' in config) ? config.left : 0) + scroll.left);
	this.set_top ((('top' in config) ? config.top : 0) + scroll.top);
	this.set_width (('width' in config) ? config.width : 100);
	this.set_height (('height' in config) ? config.height : 100);
	if ('url' in config) {
		this.navigate (config.url);
	}
};

var open_popup = function (url, left, top, width, height, event) {
	var popup;

	popup = new pseudo_popup ({
		left: left,
		top: top,
		width: width,
		height: height,
		url: url,
		callback: function (name) {
			if (name == 'destroy') {
				/*
					NB: Once the popup property is set, an attempt to remove it via 'delete'
					causes IE7 to throw an exception. That is why instead of deleting it we
					just set it to null.
				*/
				popup.get_iframe ().popup = null;
			}
		}
	});
	popup.get_iframe ().popup = popup;
	if ('preventDefault' in event) {
		event.preventDefault ();
	} else if ('returnValue' in event) {
		event.returnValue = false;
	}
}
