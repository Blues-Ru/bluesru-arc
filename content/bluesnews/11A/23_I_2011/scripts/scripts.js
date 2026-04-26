//document height
var oldDivHeight;

function getOldDivHeight(divId){
var L=layer(divId);
oldDivHeight=L.getHeight();
}
function getDivHeight(divId){
var L=layer(divId);
if (oldDivHeight < getWindowHeight() - 182 )
	L.style.height = getWindowHeight() - 182 + "px"
else if (oldDivHeight < L.getHeight())
	L.style.height = oldDivHeight + "px";
}


//preload images
function MM_swapImgRestore() { //v3.0
  var i,x,a=document.MM_sr; for(i=0;a&&i<a.length&&(x=a[i])&&x.oSrc;i++) x.src=x.oSrc;
}

function MM_preloadImages() { //v3.0
  var d=document; if(d.images){ if(!d.MM_p) d.MM_p=new Array();
    var i,j=d.MM_p.length,a=MM_preloadImages.arguments; for(i=0; i<a.length; i++)
    if (a[i].indexOf("#")!=0){ d.MM_p[j]=new Image; d.MM_p[j++].src=a[i];}}
}

function MM_findObj(n, d) { //v4.01
  var p,i,x;  if(!d) d=document; if((p=n.indexOf("?"))>0&&parent.frames.length) {
    d=parent.frames[n.substring(p+1)].document; n=n.substring(0,p);}
  if(!(x=d[n])&&d.all) x=d.all[n]; for (i=0;!x&&i<d.forms.length;i++) x=d.forms[i][n];
  for(i=0;!x&&d.layers&&i<d.layers.length;i++) x=MM_findObj(n,d.layers[i].document);
  if(!x && d.getElementById) x=d.getElementById(n); return x;
}

function MM_swapImage() { //v3.0
  var i,j=0,x,a=MM_swapImage.arguments; document.MM_sr=new Array; 
  if ((x=MM_findObj(a[0]))!=null){
  	x.oSrc=a[1]; document.MM_sr[j++]=x; if(!x.oSrc) x.oSrc=x.src; x.src=a[2];
  }  
}

//set opacity
function setElementOpacity(sElemId, nOpacity)
{
  var opacityProp = getOpacityProperty();
  var elem = document.getElementById(sElemId);

  if (!elem || !opacityProp) return;
  
  if (opacityProp=="filter")  // Internet Exploder 5.5+
  {
    nOpacity *= 100;
	
    var oAlpha = elem.filters['DXImageTransform.Microsoft.alpha'] || elem.filters.alpha;
    if (oAlpha) oAlpha.opacity = nOpacity;
    else elem.style.filter += "progid:DXImageTransform.Microsoft.Alpha(opacity="+nOpacity+")";
  }
  else 
    elem.style[opacityProp] = nOpacity;
}

function getOpacityProperty()
{
  if (typeof document.body.style.opacity == 'string') // CSS3 compliant (Moz 1.7+, Safari 1.2+, Opera 9, IE7)
    return 'opacity';
  else if (typeof document.body.style.MozOpacity == 'string') // Mozilla 1.6-, Firefox 0.8 
    return 'MozOpacity';
  else if (typeof document.body.style.KhtmlOpacity == 'string') // Konqueror 3.1, Safari 1.1
    return 'KhtmlOpacity';
  else if (document.body.filters && navigator.appVersion.match(/MSIE ([\d.]+);/)[1]>=5.5) // Internet Exploder 5.5+
    return 'filter';

  return false; 
}




