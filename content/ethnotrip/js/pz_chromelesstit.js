// Chromeless window v1.1 (TITLE)
// www.microbians.com / Gabriel Suchowolski power[z]one - powerz@microbians.com
//
// Distributed under the terms of the GNU Library General Public License
//
// - This routins are modifications based on Steinman DynAPI, so please... better use the original one. http://www.dansteinman.com/dynduo/
// - Chromeless trick by webFX. http://www.eae.net/webfx/
// - Chromeless mouse control to handled like a normal window by Gabriel Suchowolski power[z]one

//////////////////////////////////////////////////////////////// Title bar control //////

var isinit     = false;
var mywindowok = true;

var param = parent.location.search.toString()
    param = unescape( param.substring(1, param.length) )

if ( param.split("|").length>=9 ) {
	theURL 	    	    = param.split("|")[0]
	windowCERRARa 	    = param.split("|")[1]
	windowCERRARd 	    = param.split("|")[2]
	windowCERRARo 	    = param.split("|")[3]
	windowTIT 	    = param.split("|")[4]
	windowBORDERCOLOR   = param.split("|")[5]
	windowBORDERCOLORsel= param.split("|")[6]
	windowTITBGCOLOR    = param.split("|")[7]
	windowTITBGCOLORsel = param.split("|")[8]
}

var windowCERRARImg_a = new Image(); windowCERRARImg_a.src=windowCERRARa;
var windowCERRARImg_d = new Image(); windowCERRARImg_d.src=windowCERRARd;
var windowCERRARImg_o = new Image(); windowCERRARImg_o.src=windowCERRARo;


function whaitborders() {
	if ( parent.chromewinb && parent.chromewinl && parent.chromewinr ) {
		parent.chromewinb.document.bgColor=windowBORDERCOLOR
		parent.chromewinl.document.bgColor=windowBORDERCOLOR
		parent.chromewinr.document.bgColor=windowBORDERCOLOR
	} else {
		setTimeout('whaitborders()', 100);
	}
}
whaitborders()

//////////////////////////////////////////////////////////////// MOUSE MOVE //////

function mouseSTATUS() {
	this.x       = null;
	this.y       = null;
	this.bt      = "up";
	this.oldx    = null;
	this.oldy    = null;
	this.dx      = null;
	this.dy      = null;
	this.screeny = null;
	this.screenx = null;

	this.element = null;
	this.event   = null;
}

var mouse = new mouseSTATUS();

function actualizateMouseSTATUS(e) {
	if (!e) var e = event
	if ( (e.type=="mousedown" || e.type=="mouseup") && e.button!=1) return true

	var x=e.x+document.body.scrollLeft
	var y=e.y+document.body.scrollTop

	mouse.x   = x;
	mouse.y   = y;

	     if ( e.type == "mousedown" ) mouse.bt = "down";
	else if ( e.type == "mouseup" )   mouse.bt = "up";

	if (window.event) {
		mouse.screenx=window.event.screenX;
		mouse.screeny=window.event.screenY;
	} else {
		mouse.screenx=-1;
		mouse.screeny=-1;
	}

}


function initMouseEvents() {
	document.onmousedown = actualizateMouseSTATUS
	document.onmousemove = actualizateMouseSTATUS
	document.onmouseup   = actualizateMouseSTATUS
	document.onselectstart = selectstart
	document.ondragstart   = new Function("actualizateMouseSTATUS(event); return false;")
}

function selectstart(){
	if ( event.srcElement.tagName != "INPUT" && event.srcElement.tagName != "TEXTAREA") { return false; } 
	else { mouse.bt="up"; return true; }
}

initMouseEvents()

//////////////////////////////////////////////////////////////// WINDOW DRAG //////

var mywindowbt    ="up";
var wincloseSTATUS="up";

var ofx=0;
var ofy=0;
var opx=0;
var opy=0;
var px=0;
var py=0;

var wcpx1=-1, wcpy1=-1;
var wcpx2=-1, wcpy2=-1;

var wclosechanged = false;

function initToMoveWin() { 
	if (mywindowok) {
		if (wincloseSTATUS=="up" && ( mywindowbt=="up" || mywindowbt=="over") ) {
			if (isinit) {
				wcpx1 = document.all["mywindowCLOSE"].style.pixelLeft=document.body.clientWidth-18
				wcpy1 = document.all["mywindowCLOSE"].style.pixelTop =4
				wcpx2 = wcpx1 + 11 - 1 
				wcpy2 = wcpy1 + 11 - 1
				if ( mouse.x >= wcpx1 && mouse.x <= wcpx2 && mouse.y >= wcpy1 && mouse.y <= wcpy2) { 
					if (wclosechanged == false) {
						document.all["mywindowCLOSE"].document.images["closewin"].src=windowCERRARImg_o.src
						wclosechanged = true
					}
						
				} else if (wclosechanged == true) {
					document.all["mywindowCLOSE"].document.images["closewin"].src=windowCERRARImg_d.src
					wclosechanged = false
				}
			}
		}

		     if (   mouse.y <= 22 && mouse.y >= 1   && mywindowbt == "up"   && mouse.bt =="up"    ) { mywindowbt = "over" }
		else if ( ( mouse.y  > 22 || mouse.y <  1 ) && mywindowbt == "over" && mouse.bt =="up"    ) { mywindowbt = "up"   }
		else if (   mouse.y <= 22 && mouse.y >= 1   && mywindowbt == "over" && mouse.bt == "down" ) { 
			self.window.focus();
	
			if ( mouse.x >= wcpx1 && mouse.x <= wcpx2 && mouse.y >= wcpy1 && mouse.y <= wcpy2 ) { 
				wincloseSTATUS="down"
				document.all["mywindowCLOSE"].document.images["closewin"].src=windowCERRARImg_a.src
			} else {
				document.all["mywindowTITLE"].style.backgroundColor = windowTITBGCOLORsel
				document.body.style.borderColor = windowBORDERCOLORsel
				parent.chromewinb.document.bgColor=windowBORDERCOLORsel
				parent.chromewinl.document.bgColor=windowBORDERCOLORsel
				parent.chromewinr.document.bgColor=windowBORDERCOLORsel
				ofx =  mouse.x;
				ofy =  mouse.y;
				opx =  mouse.x;
				opy =  mouse.y;
			}	
			mywindowbt="down"; 
		}
		else if ( mouse.bt =="up" && mywindowbt == "down" ) { 
			mywindowbt="up"; 
			ofx=0; 
			ofy=0; 
			opx=0; 
			opy=0; 

			if ( mouse.x >= wcpx1 && mouse.x <= wcpx2 && mouse.y >= wcpy1 && mouse.y <= wcpy2 && wincloseSTATUS=="down" ) { top.window.close() }

			wincloseSTATUS="up"
		
			if ( document.all["mywindowTITLE"] ) {
				document.all["mywindowTITLE"].style.backgroundColor = windowTITBGCOLOR
				document.body.style.borderColor = windowBORDERCOLOR
				parent.chromewinb.document.bgColor=windowBORDERCOLOR
				parent.chromewinl.document.bgColor=windowBORDERCOLOR
				parent.chromewinr.document.bgColor=windowBORDERCOLOR
			}

		}
		else if ( mywindowbt == "down" && wincloseSTATUS == "up") {
			var m_scrx = mouse.screenx;
			var m_scry = mouse.screeny;
			opx = px + ofx - m_scrx;
			opy = py + ofy - m_scry;
			px = m_scrx - ofx;
			py = m_scry - ofy;
			top.window.moveTo(px , py);
		}
	}
	setTimeout('initToMoveWin()',20);
}
initToMoveWin()

//////////////////////////////////////////////////////////////// WRITE TITLE //////

function init() { 
	document.all["mywindowTITLE"].innerHTML='<table width=100% height=24 border=0 cellpadding=0 cellspacing=0><tr><td valign=middle align=left><font color=#ff9900>'+windowTIT+'</font></td></tr></table>'
	document.all["mywindowTITLE"].style.backgroundColor  = windowTITBGCOLOR
	document.all["mywindowCLOSE"].document.images["closewin"].src=windowCERRARImg_d.src;
	setTimeout('parent.main.location.replace("'+theURL+'")',200)

	isinit=true
}

