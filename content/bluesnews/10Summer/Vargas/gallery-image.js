var zoom_manager = function (config) {
	var _int_get_body_dims = function () {
		return ({
			width: document.getElementById ('main_image').offsetWidth,
			height:
				(document.body.scrollHeight > document.body.offsetHeight) ?
				document.body.scrollHeight :
				document.body.offsetHeight
		});
	};

	var _int_get_avail_dims = function () {
		return ({
			width: screen.availWidth - _dat_reserved_width,
			height: screen.availHeight - _dat_reserved_height
		});
	};

	var _dat_config;
	var _dat_current_zoom = 0;
	var _dat_extra_width = 20;
	var _dat_extra_height = 60;
	var _dat_reserved_width = 10;
	var _dat_reserved_height = 155;

	this.zoom_in = function () {
		var _int_check_increase = function () {
			var dims, zoom_old, zoom_new, new_width, new_height, avail;

			if (_dat_config.limit == false) {
				return (true);
			}
			dims = _int_get_body_dims ();
			zoom_old = Math.pow (_dat_config.step, _dat_current_zoom);
			zoom_new = Math.pow (_dat_config.step, _dat_current_zoom + 1);
			new_width =
				dims.width -
				(_dat_config.initial_width * zoom_old) +
				(_dat_config.initial_width * zoom_new) +
				_dat_extra_width;
			new_height =
				dims.height -
				(_dat_config.initial_height * zoom_old) +
				(_dat_config.initial_height * zoom_new) +
				_dat_extra_height;
			avail = _int_get_avail_dims ();
			return (
				(new_width <= avail.width) &&
				(new_height <= avail.height)
			);
		};

		if (_int_check_increase ()) {
			++_dat_current_zoom;
			this.update_window_size ();
		}
	};
	this.zoom_out = function () {
		--_dat_current_zoom;
		this.update_window_size ();
	};
	this.update_window_size = function () {
		var _int_adjust_dimensions = function () {
			var _int_get_popup = function () {
				var dom_iframes, i;

				dom_iframes = window.parent.document.getElementsByTagName ('iframe');
				for (i = 0; i < dom_iframes.length; ++i) {
					if (is_same_window (dom_iframes [i].contentWindow, window)) {
						return (dom_iframes [i].popup);
					}
				}
				return (null);
			};

			var dims, width, height, avail, popup;

			if ((popup = _int_get_popup ()) !== null) {
				dims = _int_get_body_dims ();
				width = dims.width + _dat_extra_width;
				height = dims.height + _dat_extra_height;
				avail = _int_get_avail_dims ();
				if (width > avail.width) {
					width = avail.width;
				}
				if (height > avail.height) {
					height = avail.height;
				}
				popup.set_width (width);
				popup.set_height (height);
			}
		};

		var zoom_factor, new_width, new_height, dom_obj;

		zoom_factor = Math.pow (_dat_config.step, _dat_current_zoom);
		new_width = _dat_config.initial_width * zoom_factor;
		new_height = _dat_config.initial_height * zoom_factor;
		dom_obj = document.getElementById ('main_image');
		dom_obj.style.width = new_width + 'px';
		dom_obj.style.height = new_height + 'px';
		if ((dom_obj = document.getElementById ('main_desc_top')) !== null) {
			dom_obj.style.width = new_width + 'px';
		}
		if ((dom_obj = document.getElementById ('main_desc_bottom')) !== null) {
			dom_obj.style.width = new_width + 'px';
		}
		if (window.parent) {
			setTimeout (_int_adjust_dimensions, 0);
		}
	};

	_dat_config = config;
};

var set_home_link = function () {
	if (is_same_window (window.parent, window) == false) {
		document.getElementById ('main_home_link').style.display = 'none';
	}
};

var is_same_window = function (win_1, win_2) {
	var _int_check = function (name) {
		var saved, result;

		saved = win_1.name;
		win_1.name = name;
		result = (win_2.name == name);
		win_1.name = saved;
		return (result);
	};

	return (_int_check ('One') && _int_check ('Two'));
};
