// The Central Randomizer 1.3 (C) 1997 by Paul Houle (houle@msc.cornell.edu)

rnd.today=new Date();
rnd.seed=rnd.today.getTime();

function rnd() {
        rnd.seed = (rnd.seed*9301+49297) % 233280;
        return rnd.seed/(233280.0);
};

function rand(number) {
        return Math.ceil(rnd()*number);
};

// end central randomizer.

// Determine path variable for Netscape and Explorer.

var pad = window.location.href.substring(0,window.location.href.lastIndexOf("/")+1);
var padie = window.location.href.substring(0,window.location.href.lastIndexOf("\\")+1);

if (padie.length > pad.length) { pad = padie}

//~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~CROSS BROWSER DHTML FUNCIONS [START]

var screenW;var screenH;
var maxPopW;var maxPopH;
var stageW; var stageH;
var yourBrowser = "";
var NN;
var endDiv;
var IEd = 'document.all.';
var IEs = '.style';
var mouseX = 100;var mouseY = 100;
var yourPlatform = "";
var directorHere = false;
var flashHere = false;
var midiHere = true;
var flashAccess = false;

function dInitialize()
{
//=======================DHTML vars
if ( document.layers ) { NN = true; } else { NN = false; }
if ( NN ) { endDiv = '</LAYER>'; } else { endDiv = '</DIV>'; };

//=======================browser detection
if ( navigator.appName == "Microsoft Internet Explorer" )
	{
	var bigVersionNumber = navigator.userAgent.substring(navigator.userAgent.indexOf('MSIE') + 5, navigator.userAgent.lastIndexOf(';'));
	if ( parseFloat(bigVersionNumber) >= 4 ) { yourBrowser = "IE4";}
	else { yourBrowser = "IE3";	};
	}
else if ( navigator.appName == "Netscape" )
	{
	var bigVersionNumber = navigator.appVersion.substring(0,navigator.appVersion.indexOf(' '));
	if ( parseFloat(bigVersionNumber) >= 4 ) { yourBrowser = "NS4";	}
	else if ( parseFloat(bigVersionNumber) >= 3 ) {	yourBrowser = "NS3";}
	else { yourBrowser = "NS2";	};
	};

//=======================platform detection
if ( navigator.appVersion.indexOf("Mac") != -1 ) { yourPlatform = "Mac" }
else { yourPlatform = "notMac" };

//=======================screen size detection
screenW = screen.width;
screenH = screen.height;
maxPopW = screenW;
maxPopH = screenH;
if ( yourPlatform == "Mac" ) { maxPopH = screenH - 20; };
if ( yourBrowser == "IE4" ) { maxPopW = screenW - 10; maxPopH = screenH - 50; };

//=======================plugin detection
if ( navigator.mimeTypes && navigator.mimeTypes.length )
	{
	mimeDirector = navigator.mimeTypes["application/x-director"]
	mimeFlash = navigator.mimeTypes["application/x-shockwave-flash"]
	mimeMidi = navigator.mimeTypes["audio/x-midi"]
	if ( mimeDirector ) { if ( mimeDirector.enabledPlugin ) { directorHere = true; }; };
	if ( mimeFlash ) { if ( mimeFlash.enabledPlugin ) { flashHere = true; }; };
	if ( mimeMidi ) { if ( mimeMidi.enabledPlugin ) { } else { midiHere = false; }; };
	}
else
	{
	//if ( confirm('Do you have the Macromedia Shockwave for Director plugin?') ) { directorHere = true; }
	//else if ( confirm('Do you want it?') ) { window.open("http://www.macromedia.com","",""); };
	//if ( confirm('Do you have the Macromedia Shockwave Flash plugin?') ) { flashHere = true; }
	//else if ( confirm('Do you want it?') ) { window.open("http://www.macromedia.com","",""); };
	//All browsers come with a MIDI plugin, I think
	};

if ( flashHere && navigator.javaEnabled() ) { flashAccess = true; };
};

function dStage()
{
if ( NN ) { stageW = window.innerWidth; stageH = window.innerHeight; }
else { stageW = document.body.offsetWidth; stageH = document.body.offsetHeight; };
};

function dMakeSimpleDiv(thisHTML,thisName,thisX,thisY,thisW,thisH,thisColor,thisTile,thisVisibility,thisMethod)
{
thisCode = ''
+ dOpenDiv(thisHTML,thisName,thisX,thisY,thisW,thisH,thisColor,thisTile,'none','none','none','none','none','none',thisVisibility,'',thisMethod) + '\n'
+ thisHTML
+ endDiv
if ( thisMethod == 'get' ) { return thisCode; } else { document.write(thisCode);return null; };
};


function dMakeDiv(thisHTML,thisName,thisX,thisY,thisW,thisH,thisColor,thisTile,thisZ,clipL,clipT,clipR,clipB,thisClassN,thisVisibility,thisExtra,thisMethod)
{
thisCode = ''
+ dOpenDiv(thisHTML,thisName,thisX,thisY,thisW,thisH,thisColor,thisTile,thisZ,clipL,clipT,clipR,clipB,thisClassN,thisVisibility,thisExtra,thisMethod) + '\n'
+ thisHTML + '\n'
+ endDiv
if ( thisMethod == 'get' ) { return thisCode; } else { document.write(thisCode);return null; };
};

function dOpenDiv(thisHTML,thisName,thisX,thisY,thisW,thisH,thisColor,thisTile,thisZ,clipL,clipT,clipR,clipB,thisClassN,thisVisibility,thisExtra,thisMethod)
{
if ( thisX != 'none' && isNaN(thisX) && thisX.indexOf('%') == -1 ) { thisX = Math.round(eval(thisX)); };
if ( thisY != 'none' && isNaN(thisY) && thisY.indexOf('%') == -1 ) { thisY = Math.round(eval(thisY)); };
if ( thisW != 'none' && isNaN(thisW) && thisW.indexOf('%') == -1 ) { thisW = Math.round(eval(thisW)); };
if ( thisH != 'none' && isNaN(thisH) && thisH.indexOf('%') == -1 ) { thisH = Math.round(eval(thisH)); };
if ( thisColor == 'none' ) { thisBg = ''; }
else
	{
	if ( NN ) { thisBg = ' BGCOLOR="#' + thisColor + '"'; }
	else { thisBg = 'BACKGROUND-COLOR:#' + thisColor + ';'; };
	};

if ( thisZ == 'none' ) { thisZix = ''; }
else
	{
	if ( NN ) { thisZix = ' Z-INDEX=' + thisZ; }
	else { thisZix = 'Z-INDEX:' + thisZ + ';'; };
	};

if ( clipL == 'none' ) { thisClip = ''; }
else
	{
	if ( NN ) { thisClip = ' CLIP=' + clipL + ',' + clipT + ',' + clipR + ',' + clipB; }
	else { thisClip = 'CLIP:rect(' + clipT + 'px ' + clipR + 'px ' + clipB + 'px '+ clipL + 'px);'; };
	};

if ( thisClassN == 'none' ) { thisClass = ''; }
else
	{
	if ( NN ) { thisClass = ' CLASS="' + thisClassN + '"'; }
	else { thisClass = ' CLASS="' + thisClassN + '"'; };
	};

if ( document.layers ) { thisCode = '<LAYER NAME="' + thisName + '" LEFT=' + thisX + ' TOP=' + thisY + ' WIDTH=' + thisW + ' HEIGHT=' + thisH + thisBg + thisZix + thisClip + ' BACKGROUND="' + thisTile + '" VISIBILITY="' + thisVisibility + '" ' + thisClass + ' ' + thisExtra + '>'; }
else { thisCode = '<DIV ID="' + thisName + '" STYLE="POSITION:absolute;LEFT:' + thisX + ';TOP:' + thisY + ';WIDTH:' + thisW + ';HEIGHT:' + thisH + ';' + thisBg + thisZix + thisClip + 'BACKGROUND-IMAGE:url(' + thisTile + ');VISIBILITY:' + thisVisibility + ';"' + thisClass + ' ' + thisExtra + '>'; };
return thisCode;
};

function dWrite(thisO,thisP,thisText)
{
if ( NN ) { thisDiv = eval(thisP + thisO); thisDiv.document.open(); thisDiv.document.write(thisText); thisDiv.document.close(); }
else { thisDiv = eval(IEd + thisO); thisDiv.innerHTML = thisText; };
};

function dMove(thisO,thisP,thisX,thisY)
{
if ( NN ) { thisDiv = eval(thisP + thisO); }
else { thisDiv = eval(IEd + thisO + IEs); };
if ( thisX != 'none' ) { thisDiv.left = eval(thisX); };
if ( thisY != 'none' ) { thisDiv.top = eval(thisY); };
};

function dMoveBy(thisO,thisP,thisX,thisY)
{
if ( thisX == 'none' ) { thisX = 0; }; if ( thisY == 'none' ) { thisY = 0; };
if ( isNaN(thisX) ) { thisX = eval(thisX); }; if ( isNaN(thisY) ) { thisX = eval(thisY); };
if ( NN ) { thisDiv = eval(thisP + thisO); thisDiv.left = thisDiv.left + thisX; thisDiv.top = thisDiv.top + thisY; }
else { thisDiv = eval(IEd + thisO + IEs); thisDiv.left = thisDiv.pixelLeft + eval(thisX); thisDiv.top = thisDiv.pixelTop + eval(thisY); };
};

function dMoveStraight(thisO,thisP,endX,endY,thisTime,thisVal,endFunction)
{
var curX = dMeasure(thisO,thisP,'left');var curY = dMeasure(thisO,thisP,'top');
var spaceX = endX - curX;var spaceY = endY - curY;
if ( endX >= curX ) { var compX = '< ' + endX; } else { var compX = '> ' + endX; };if ( endY >= curY ) { var compY = '< ' + endY; } else { var compY = '> ' + endY; };
startDate = new Date();startMoment = startDate.getTime();
thisFunction = ''
+ 'stepDate = new Date();stepMoment = stepDate.getTime();'
+ 'thisPart = ' + thisTime + ' / (stepMoment-' + startMoment + ');'
+ 'thisMoveX = ' + curX + '+' + spaceX + ' / thisPart;'
+ 'thisMoveY = ' + curY + '+' + spaceY + '/ thisPart;'
+ 'if ( thisMoveX ' + compX + ' || thisMoveY ' + compY + ' ) {'
+ 'dMove("' + thisO + '","' + thisP + '",thisMoveX,thisMoveY);'
+ '} else { '
+ 'dMove("' + thisO + '","' + thisP + '",' + endX + ',' + endY + ');'
+ 'clearInterval(' + thisVal + ');'
+ endFunction
+ '};';
eval(thisVal + ' = setInterval(thisFunction,50);');
};

function dShow(thisO,thisP,thisState)
{
if ( NN ) { thisDiv = eval(thisP + thisO); }
else { thisDiv = eval(IEd + thisO + IEs); };
thisDiv.visibility = thisState;
};

function dVisible(thisO,thisP)
{
if ( NN ) { thisDiv = eval(thisP + thisO); }
else { thisDiv = eval(IEd + thisO + IEs); };
if ( thisDiv.visibility == 'show' ) { return true; } else { return false; };
};

function dColor(thisO,thisP,thisColor)
{
if ( NN ) { thisDiv = eval(thisP + thisO); thisDiv.bgColor = '#' + thisColor; }
else { thisDiv = eval(IEd + thisO + IEs); thisDiv.background = '#' + thisColor; };
};

function dBackground(thisO,thisP,thisPic)
{
//if ( NN ) { thisDiv = eval(thisP + thisO); thisDiv.background.src = thisPic; }
if ( NN ) { thisDiv = eval(thisP + thisO); thisDiv.document.open();thisDiv.document.write('<HTML><BODY BACKGROUND="' + thisPic + '"></BODY></HTML>');thisDiv.document.close(); }
else { thisDiv = eval('document.all.' + thisObject + '.style'); thisDiv.backgroundImage = "url(" + thisPic + ")"; };
};

function dMeasure(thisO,thisP,thisM)
{
if ( NN )
	{
	thisDiv = eval(thisP + thisO);
	if ( thisM == 'left' ) { return thisDiv.left; }
	else if ( thisM == 'top' ) { return thisDiv.top; }
	else if ( thisM == 'width' ) { return thisDiv.clip.width; }
	else if ( thisM == 'height' ) { return thisDiv.clip.height; }
	}
else
	{
	thisDiv = eval(IEd + thisO + IEs); 
	if ( thisM == 'left' ) { return thisDiv.pixelLeft; }
	else if ( thisM == 'top' ) { return thisDiv.pixelTop; }
	else if ( thisM == 'width' ) { return thisDiv.pixelWidth; }
	else if ( thisM == 'height' ) { return thisDiv.pixelHeight; }
	};
};

function dSize(thisO,thisP,thisW,thisH)
{
if ( NN )
	{
	thisDiv = eval(thisP + thisO);
	if ( thisW != 'none' ) { thisDiv.clip.width  = thisW; }
	if ( thisH != 'none' ) { thisDiv.clip.height = thisH; }
	}
else
	{
	thisDiv = eval(IEd + thisO + IEs); 
	if ( thisW != 'none' ) { thisDiv.width  = thisW; }
	if ( thisH != 'none' ) { thisDiv.height = thisH; }
	};
};

function dSizeBy(thisO,thisP,thisW,thisH)
{
if ( NN )
	{
	thisDiv = eval(thisP + thisO);
	if ( thisW != 'none' ) { thisDiv.clip.width  = thisDiv.clip.width + thisW; }
	if ( thisH != 'none' ) { thisDiv.clip.height = thisDiv.clip.height + thisH; }
	}
else
	{
	thisDiv = eval(IEd + thisO + IEs); 
	if ( thisW != 'none' ) { thisDiv.width  = thisDiv.pixelWidth + thisW; }
	if ( thisH != 'none' ) { thisDiv.height = thisDiv.pixelHeight + thisH; }
	};
};

function dImgSrc(thisO,thisP,thisI)
{
if ( NN ) { thisPic = eval(thisP + 'images["' + thisO + '"]'); }
else { thisPic = eval('document.' + thisO ); };
thisPic.src = thisI;
};

function dPlaySound(thisO,thisP,thisN)
{
if ( NN ) { thisDiv = eval(thisP + 'embeds["' + thisO + '"]'); }
else { thisDiv = eval('document.' + thisO); };
thisDiv.GotoFrame(thisN);
thisDiv.Play();
};

function dPop(thisHTML,thisFile,thisX,thisY,thisW,thisH,thisIW,thisIH,thisOW,thisOH,thisStatus,thisMenu,thisResize,thisScroll,thisName)
{
theseM = ''
if ( thisX != '' ) { theseM = theseM + 'LEFT=' + eval(thisX) + ','; };
if ( thisY != '' ) { theseM = theseM + 'TOP=' + eval(thisY) + ','; };
if ( thisX != '' ) { theseM = theseM + 'screenX=' + eval(thisX) + ','; };
if ( thisY != '' ) { theseM = theseM + 'screenY=' + eval(thisY) + ','; };
if ( thisW != '' ) { theseM = theseM + 'WIDTH=' + eval(thisW) + ','; };
if ( thisH != '' ) { theseM = theseM + 'HEIGHT=' + eval(thisH) + ','; };
if ( thisIW != '' ) { theseM = theseM + 'INNERWIDTH=' + eval(thisIW) + ','; };
if ( thisIH != '' ) { theseM = theseM + 'INNERHEIGHT=' + eval(thisIH) + ','; };
if ( thisOW != '' ) { theseM = theseM + 'OUTERWIDTH=' + eval(thisOW) + ','; };
if ( thisOH != '' ) { theseM = theseM + 'OUTERHEIGHT=' + eval(thisOH) + ','; };

theseParameters = theseM + 'TOOLBAR=no,LOCATION=no,DIRECTORIES=no,STATUS=' + thisStatus + ',MENUBAR=' + thisMenu + ',RESIZABLE=' + thisResize + ',SCROLLBARS=' + thisScroll

//if ( NN )
//	{
	eval(thisName + ' = window.open("' + thisFile + '","' + thisName + '","' + theseParameters + '")');
	if ( thisHTML != '' ) { eval(thisName + '.document.open();' + thisName + '.document.write(thisHTML);' + thisName + '.document.close();' + thisName + '.focus();') };
//	}
//else
//	{
//	popWindow = window.open("iepop.html","' + thisName + '","WIDTH=" + thisW + ",HEIGHT=" + thisH + ",TOOLBAR=no,LOCATION=no,DIRECTORIES=no,MENUBAR=yes,RESIZABLE=yes,SCROLLBARS=yes");
//	//popWindow.document.open();popWindow.document.write(thisHTML); popWindow.document.close(); popWindow.focus();
//	};
};

function dCapture()
{
if ( NN )
	{
	window.captureEvents(Event.MOUSEUP|Event.MOUSEDOWN|Event.MOUSEMOVE);
	thisWindow = 'window';
	}
else
	{
	thisWindow = 'document';
	};
eval(thisWindow + '.onmousedown = mDown');
eval(thisWindow + '.onmouseup = mUp');
eval(thisWindow + '.onmousemove = mMove');
};

function dGetMouse(e)
{
if ( NN ) { mouseX = e.pageX; mouseY = e.pageY; }
else { mouseX = window.event.clientX ; mouseY = window.event.clientY; };
};

//~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~CROSS BROWSER DHTML FUNCIONS [END]

//dInitialize();
