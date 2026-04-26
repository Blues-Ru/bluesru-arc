$.extend({
	evIE: function(command){
		if(!$.browser.msie){return command;}
		switch(command){
			case 'slideToggle':
				return 'toggle';
			case 'slideUp':
				return 'hide';
			case 'slideDown':
				return 'show';
		}
	},
	evScrollTop: function(){
		var $body=$('body');
		return Math.max($body[0].scrollTop,$body.parent()[0].scrollTop);
	},
	evScreenHeight: function(){
		var $body=$('body');
		return Math.max($body[0].clientHeight,$body.parent()[0].clientHeight);
	},
	evScrollHeight: function(){
		var $body=$('body');
		return Math.max($body[0].scrollHeight,$body.parent()[0].scrollHeight);
	},
	validateEmail: function(input_or_string){
		//проверяем передана ли строка
		if(typeof input_or_string=='string'){
			var email=input_or_string;
		}else{
			//проверяем передан ли тег
			if(typeof input_or_string.value=='string'){
				var email=input_or_string.value;
			}else{
				//проверяем передан ли объект jQuery
				if(typeof input_or_string[0].value=='string'){
					var email=input_or_string[0].value;
				}else{
					return false;
				}
			}
		}
		return (email.search(/^[^@\s]+@[^@\s]+\.[^@\s]{2,}$/)==0);
	},
	/*уже появился в jquery
	trim: function(str){
		str=str.replace(/^[\s]+/,'');
		str=str.replace(/[\s]+$/,'');
		return str;
	},*/
	popup: function(url,w,h,hash){
		var hash=(hash || {});
		var name=(hash.name || '_blank');
		if(!(window.screen 
			&& window.screen.height 
			&& window.screen.height > (h+50) 
			&& window.screen.width 
			&& window.screen.width > (w+50)
		)){
			w=(window.screen.width>(w+50))?(w+25):(window.screen.width-50);
			h=(window.screen.height>(h+50))?(h+25):(window.screen.height-50);
			hash.s=1;
		}
		var left=($.getCookie('lastPopupLeft') || 75);
		left=parseInt(left)+ 25;
		if(window.screen && window.screen.width && left+parseInt(w)>window.screen.width)left=50;
		$.setCookie('lastPopupLeft',left);
		var top=($.getCookie('lastPopupTop') || 75);
		top=parseInt(top)+ 25;
		if(window.screen && window.screen.height && top+parseInt(w)>window.screen.height)top=50;
		$.setCookie('lastPopupTop',top);
		var params='';
		params+='left='+ parseInt(left)+ ',';
		params+='top='+ parseInt(top)+ ',';
		params+='width='+ parseInt(w)+ ',';
		params+='height='+ parseInt(h)+ ',';
		params+='scrollbars='+ (hash.s || hash.scroll || hash.scrollbars || '0')+ ',';
		params+='resizable='+ (hash.r || hash.resize || hash.resizable || '0')+ ',';
		params+='menubar='+ (hash.m || hash.menu || hash.menubar || '0')+ ',';
		//params+='titlebar='+ (hash.titlebar || '0')+ ',';
		params+='toolbar='+ (hash.toolbar || '0')+ ',';
		params+='location='+ (hash.location || '0')+ ',';
		//params+='directories='+ (hash.directories || '0')+ ',';
		//params+='hotkeys='+ (hash.hotkeys || '0')+ ',';
		params+='status='+ (hash.status || '0')+ ',';
		//params+='dependent='+ (hash.dependent || '0')+ ',';
		//if(hash.fullscreen){params+='fullscreen='+ hash.fullscreen+ ',';}
		//params+='channelmode='+ (hash.channelmode || '0');
		//alert(params);
		var win=window.open(url,name,params);
		try{
			win.focus();
			return win;
		}catch(e){}
	},
	props: function(hash){
		var result='';
		for(var i in hash){
			result+=''+ i+ ': '+ hash[i]+ '\n';
		}
		return result;
	},
	tryUntil: function(function2run,testCondition){
		var testCondition=unescape(testCondition);
		var function2run=unescape(function2run);
		if(eval(testCondition)){
			try{
				eval(function2run);
			}catch(e){/*поскольку событие было отложено, возможно что к моменту реализации функция уже перестанет существовать*/}
		}else{
			var date=new Date();
			var mls=parseInt(arguments[2] || 100);
			setTimeout('$.tryUntil("'+ escape(function2run)+ '","'+ escape(testCondition)+ '",'+ mls+ ')',mls);
		}
	},
	ctrlEnter: function(event){//отслеживает нажатие ctrl Enter
		if(event.keyCode==13 && event.ctrlKey){
			return true;
		}
		return false;
	},
	newin: function(link){
		if(link && link.href){
			var newin=window.open(link.href);
			return false;
		}
	},
	postfix: function(num,one,two,five){
		var rest=num%10;
		if(rest==1 && num%100!=11){
			return one;
		}else if(rest>=2 && rest<=4 && num%100!=12 && num%100!=13 && num%100!=14){
			return two;
		}else{
			return five;
		}
	},
	decryptText: function(text){
		var result='';
		var arr=text.split(',');
		var log='';
		for(var i=0; i<arr.length; i++){
			var sym=arr[i];
			log+='i='+i+', sym='+sym+'';
			if(parseInt(sym)>0){
				result+=String.fromCharCode(parseInt(sym));
			}else{
				result+=sym;
			}
		}
		return result;
	},
	decryptTextWrite: function(text){
		document.write($.decryptText(text));
	},
	setCookie: function(cookieName,cookieContent,cookieExpireTime){//cookieExpireTime в часах
		if(cookieExpireTime>0){
			var expDate=new Date();
			expDate.setTime(expDate.getTime()+cookieExpireTime*1000*60*60);
			var expires=expDate.toGMTString();
			document.cookie=cookieName+"="+escape(cookieContent)+"; path="+escape('/')+"; expires="+expires;
		}else{
			document.cookie=cookieName+"="+escape(cookieContent)+"; path="+escape('/')+"";
		}
	},
	getCookie: function(cookieName){
		var ourCookie=document.cookie;
		if(!ourCookie || ourCookie=="")return "";
			ourCookie=ourCookie.split(";");
		var i=0;
		var Cookie;
		while(i<ourCookie.length){
			Cookie=ourCookie[i].split("=")[0];
			if(Cookie.charAt(0)==" ")
				Cookie=Cookie.substring(1);
			if(Cookie==cookieName){
				return unescape(ourCookie[i].split("=")[1]);
			}
			i++;
		}
		return ""
	}
})

$.fn.extend({
	evDragDrop: function(hash){
		//придумываем идентификатор объекту, чтобы отличать его от других
		var $target=this;
		var random_id='random_id_'+Math.random().toString().substr(2);
		if(!C.__evDragDrop__)C.__evDragDrop__=[];
		C.__evDragDrop__[random_id]={};
		//реагируем на нажатие
		$target.mousedown(function(evt){
			evt.preventDefault();
			C.__evDragDrop__[random_id].is_drag=true;
			C.__evDragDrop__[random_id].drag_xy=[evt.clientX,evt.clientY]
				if(hash.callback){
					hash.callback({
						event: evt,
						type: 'start',
						left: $target[0].offsetLeft,
						top: $target[0].offsetTop
					});
				}
		});
		//реагируем на drug
		$('body').mousemove(function(evt){
			evt.preventDefault();
			if(C.__evDragDrop__[random_id].is_drag){
				var delta=[
					evt.clientX-C.__evDragDrop__[random_id].drag_xy[0],
					evt.clientY-C.__evDragDrop__[random_id].drag_xy[1]
				];
				var new_lt=[
					$target[0].offsetLeft+delta[0],
					$target[0].offsetTop+delta[1]
				];
				var lt=new_lt;
				//преобразуем новые координаты так, чтобы объект не вылезал за рамки
				if(hash.left){
					if(lt[0]<hash.left[0])lt[0]=hash.left[0];
					if(lt[0]>hash.left[1])lt[0]=hash.left[1];
				}
				if(hash.top){
					if(lt[1]<hash.top[0])lt[1]=hash.top[0];
					if(lt[1]>hash.top[1])lt[1]=hash.top[1];
				}
				//позициорируем
				$target.css({'left':lt[0],'top':lt[1]});
				C.__evDragDrop__[random_id].drag_xy=[evt.clientX + (lt[0]-new_lt[0]), evt.clientY + (lt[1]-new_lt[1])];
				if(hash.callback){
					hash.callback({
						event: evt,
						type: 'drag',
						left: lt[0],
						top: lt[1]
					});
				}
			}
		});
		//реагируем на drop
		$('body').mouseup(function(evt){//привязываем событие к document, потому что нам не важны координаты
			evt.preventDefault();
			if(C.__evDragDrop__[random_id].is_drag){
				//если происходит перетаскивание, то заканчиваем его
				C.__evDragDrop__[random_id].drag_xy=[];
				C.__evDragDrop__[random_id].is_drag=false;
				if(hash.callback){
					hash.callback({
						event: evt,
						type: 'drop',
						left: $target[0].offsetLeft,
						top: $target[0].offsetTop
					});
				}
			}
		});
	},
	evTop50: function(){
		var top=$.evScrollTop()+ ($.evScreenHeight() -this[0].offsetHeight)/2;
		this.css({top:top});
	},
	evSwitchField: function(value){//в зависимости от фокуса показывает или скрывает текст value
		if(this.attr('type')!='password'){
			var value=(value || this.attr('value'));
			this.evSwitchInputField(value);
		}else{
			var value=(value || 'Пароль');
			this.evSwitchPasswordField(value);
		}
	},
	evSwitchInputField: function(value){
		this.bind('focus blur',function(event){
			if(event.type=='focus' && $.trim(event.target.value)==value){
				event.target.value='';
			}else if(event.type=='blur' && $.trim(event.target.value)==''){
				event.target.value=value;
			}
		}).trigger('blur');
	},
	evSwitchPasswordField: function(value){//в зависимости от фокуса переключает поле типа password в тип text и показывает в нем текст (value) 
		this.bind('focus blur',function(event){
			var field_name=this.name;
			if(event.type=='focus' && event.target.value==value){
				var $parent=$(this).parent();
				$parent.empty().append(
					$('<input>').attr({
						type:'password',
						name:field_name,
						maxlength:16
					})
				).children()[0].focus();
				$parent.children().evSwitchPasswordField(value,true);
			}else if(event.type=='blur' && event.target.value==''){
				var $parent=$(this).parent();
				$parent.empty().append(
					$('<input>').attr({
						name:field_name,
						maxlength:16,
						value:value
					})
				).children()[0];
				$parent.children().evSwitchPasswordField(value,true);
			}
		});
		if(!arguments[1] && this.attr('type')=='password'){
			this.trigger('blur');
		}
	},
	evCorrectURL: function(){//функция вешается на blur, добавляет http:// и убирает конечный слэш
		var url=$.trim(this.attr('value'));
		//с адресом все ОК если:
		if(false 
			|| !url //или еще ничего не набрали
			|| url.search(/:\/\//)>0 //или http:// уже набрали
			|| url.search(/\./)==-1 //или пока не набрали ни одной точки
		){
			//ничего не делаем
		}else{
			//добавляем "http://" если:
			if(true
				&& url.search(/:\/\//)==-1 // "http://" еще не набрали
				&& url.search(/\.(ru|su|net|com|org|biz|info|tv)/)>0 //в адресе присутствует какой-то из основных доменов 1 уровня
			){
				url='http://'+ url;
			}
		}
		//убираем конечный слэш, если:
		if(true
			&& url.search(/\/$/)>0 //конечный слэш имеется
			&& url.search(/:\/\//)>0 //в адресе имеется http://
			&& url.match(/\//g).length==3 //нет других слэшей кроме последнего и двух рядом в http://
		){
			url=url.substr(0,url.length-1);
		}
		this.attr('value',url);
	},
	evSboxSelect: function(value){
		var sbox=this[0];
		if(sbox.tagName=='SELECT'){
			var ops=sbox.options;
			for(var i=0; i<ops.length; i++){
				if(ops[i].value==value){
					ops.selectedIndex=i;
					break;
				}
			}
		}
	},
	evSboxValue: function(){
		var sbox=this[0];
		var index=sbox.options.selectedIndex;
		var current=sbox.options[index].value;
		return current;
	}
})