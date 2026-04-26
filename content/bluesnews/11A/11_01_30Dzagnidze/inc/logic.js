//Copyright 2008 S10 Software. All rights reserved.

var mbIE = false;
var mbDhtml = false;
var mbOpera = false;
var mbAll = false;
var msSize = 'M';
var mnPos = 0;
var mbAuto = false;
var mbTimerRunning = false;
var mnProgress = 0;
var msTextBg = '';
var msPhotoBg = '';
var msTrans = null;
var msBorderBegin = '';
var msBorderEnd = '';
var moNextImg = null;
var mnNextPos = -1;
var mnPrevPos = -1;
var mnCurTransition = mnTransition;
var mbHideKeyTips = false;
var msWord = null;
var moHta = null;

init();

//--------------------

function init()
{
	var s = navigator.userAgent;
	mbIE = ((s.indexOf('MSIE') != -1) && (window.createPopup != null));  //IE 5.5 and up
	mbOpera = (s.indexOf('Opera') != -1);
	mbDhtml = (document.getElementById != null);

	if (mbIE && (location.href.toLowerCase().indexOf('index.htm') == -1))
	{
		location.replace('index.htm');
		return;
	}

	if ((window.screen != null) && (screen.width <= 800) && (msSizes.charAt(0) == 'S') && (mnDim2 >= 600)) msSize = 'S';
	var s = location.href.split('?');
	if (s.length == 1) s = location.href.split('#');
	if (s.length == 1)
	{
		if (msDefaultPage == 'I') mbAll = true;
	}
	if (s.length > 1)
	{
		s = s[1].split('_');
		if (s[0] == '0')
			mbAll = true;
		else
		{
			mnPos = s[0] - 1;
			if (mnPos < 0) mnPos = 0;
			else if (mnPos >= mnTot) mnPos = mnTot - 1;
		}
		if (s.length > 1)
		{
			if ((s[1] == 'L') || (s[1] == 'M') || (s[1] == 'S')) msSize = s[1];
			if (!mbIE && mbDhtml && (s.length > 2))
			{
				if (!mbAll && (s[2] == 'A') && (mnPos < (mnTot - 1))) mbAuto = true;
				if (s.length > 3) mbHideKeyTips = true;
			}
		}
	}

	msTextBg = msPhotoBg = ' bgcolor="' + msTextBgColor + '"';
	if (msTextBgPattern != '')
	{
		msTextBg += ' background="inc/textBg.' + msTextBgPatternType + '"';
		if (msTextBgPattern.charAt(msTextBgPattern.length - 1) != '_')
			msPhotoBg = msTextBg;
	}
	msTextColor = '#' + msTextColor;
	if (msTextBgColor != '') msTextBgColor = '#' + msTextBgColor;
	msBgColor = '#' + msBgColor;
	msBgTextColor = '#' + msBgTextColor;
	msBorderColor = '#' + msBorderColor;

	if (mbDhtml)
	{
		var oImgBtn2 = document.createElement('IMG');
		oImgBtn2.src = 'inc/button2.gif';
	}

	if (mbIE)
	{
		moNextImg = document.createElement('IMG');
		moNextImg.onload = onNextImgLoad;

		msTrans = new Array();
		msTrans[0] = 'Barn,Motion=In/Out,Orientation=Horizontal/Vertical';
		msTrans[1] = 'Blinds,Bands=4/8/16/32,Direction=Up/Down/Up/Down';
		msTrans[2] = 'Checkerboard,Direction=Left/Right,SquaresX=4/8/16/32/64,SquaresY=4/8/16/32/64';
		msTrans[3] = 'Checkerboard,Direction=Up/Down,SquaresX=4/8/16/32/64,SquaresY=4/8/16/32/64';
		msTrans[4] = 'Fade,Overlap=1';
		msTrans[5] = 'GradientWipe,GradientSize=.1/.2/.4,WipeStyle=0,Motion=Forward/Reverse';
		msTrans[6] = 'GradientWipe,GradientSize=.1/.2/.4,WipeStyle=1,Motion=Forward/Reverse';
		msTrans[7] = 'Inset';
		msTrans[8] = 'Iris,IrisStyle=Circle/Diamond,Motion=In/Out';
		msTrans[9] = 'Iris,IrisStyle=Cross/Plus,Motion=In/Out';
		msTrans[10] = 'Iris,IrisStyle=Square/Star,Motion=In/Out';
		msTrans[11] = 'RadialWipe,WipeStyle=Clock';
		msTrans[12] = 'RadialWipe,WipeStyle=Wedge';
		msTrans[13] = 'RadialWipe,WipeStyle=Radial';
		msTrans[14] = 'RandomDissolve';
		msTrans[15] = 'Spiral,GridSizeX=16,GridSizeY=16';
		msTrans[16] = 'Strips,Motion=LeftUp/LeftDown/RightUp/RightDown';
		msTrans[17] = 'Wheel,Spokes=2/4/8';
		msTrans[18] = 'Wheel,Spokes=16/32';
		msTrans[19] = 'Zigzag,GridSizeX=8,GridSizeY=8';

		msTrans['Forward'] = 'GradientWipe,GradientSize=.1,WipeStyle=0,Motion=Forward';
		msTrans['Reverse'] = 'GradientWipe,GradientSize=.1,WipeStyle=0,Motion=Reverse';
	}

	if (mnBorder == 1)
	{
		msBorderBegin = '<table border=0 cellpadding=0 cellspacing=0><tr><td colspan=3 bgcolor=' + msBorderColor + '><img src=inc/p.gif width=1 height=1 hspace=0 vspace=0></td></tr><tr><td bgcolor=' + msBorderColor + '><img src=inc/p.gif width=1 height=1 hspace=0 vspace=0></td><td align=center>';
		msBorderEnd = '</td><td bgcolor=' + msBorderColor + '><img src=inc/p.gif width=1 height=1 hspace=0 vspace=0></td></tr><tr><td colspan=3 bgcolor=' + msBorderColor + '><img src=inc/p.gif width=1 height=1 hspace=0 vspace=0></td></tr></table>';
	}
	else if (mnBorder == 2)
	{
		msBorderBegin = '<table border=0 cellpadding=0 cellspacing=0><tr><td bgcolor=' + msBorderColor + ' colspan=2><img src=inc/p.gif width=1 height=1 hspace=0 vspace=0></td><td background=inc/borderR.gif rowspan=2><img src=inc/p.gif width=7 height=1 hspace=0 vspace=0></td></tr><tr><td bgcolor=' + msBorderColor + '><img src=inc/p.gif width=1 height=1 hspace=0 vspace=0></td><td align=center>';
		msBorderEnd = '</td></tr><tr><td background=inc/borderB.gif colspan=2><img src=inc/p.gif width=1 height=7 hspace=0 vspace=0></td><td><img src=inc/borderRB.gif width=7 height=7 hspace=0 vspace=0></td></tr></table>';
	}
	else if (mnBorder == 3)
	{
		msBorderBegin = '<table border=0 cellpadding=0 cellspacing=0><tr><td><img src=inc/borderLT.gif width=8 height=8 hspace=0 vspace=0></td><td background=inc/borderH.gif><img src=inc/p.gif width=8 height=8 hspace=0 vspace=0></td><td><img src=inc/borderRT.gif width=8 height=8 hspace=0 vspace=0></td></tr><tr><td background=inc/borderV.gif><img src=inc/p.gif width=8 height=8 hspace=0 vspace=0></td><td align=center>';
		msBorderEnd = '</td><td background=inc/borderV.gif><img src=inc/p.gif width=8 height=8 hspace=0 vspace=0></td></tr><tr><td><img src=inc/borderLB.gif width=8 height=8 hspace=0 vspace=0></td><td background=inc/borderH.gif><img src=inc/p.gif width=8 height=8 hspace=0 vspace=0></td><td><img src=inc/borderRB.gif width=8 height=8 hspace=0 vspace=0></td></tr></table>';
	}

	msWord = msLang.split('|');
	if (msWord[3] != '') msWord[3] += ':';
	if (mbHome && (msHomeCaption == '')) msHomeCaption = 'Home';
	if (mbHome && (msHomeURL == '')) msHomeURL = '../';

	var docTitle = stripTags(msAlbumTitle.replace(/<br>/g, ' ')).replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&quot;/g, '"').replace(/&amp;/g, '&');
	if (docTitle.indexOf('&'))
		try
		{
			var elem = document.createElement('div');
			elem.innerHTML = docTitle;
			if (elem.innerText) docTitle = elem.innerText;
			else if (elem.textContent) docTitle = elem.textContent;
		}
		catch(e) {}
	document.title = docTitle;
	document.write('<meta http-equiv=MSThemeCompatible content=yes>');

	//Render the body:
	document.write('<body text=' + msTextColor + ' link=' + msBgTextColor + ' alink=' + msBgTextColor + ' vlink=' + msBgTextColor + ' bgcolor=' + msBgColor + ((msBgPattern != '') ? ' background=inc/pageBg.' + msBgPatternType : '') + ' style=margin:0;font-family:arial,sans-serif; topmargin=0 leftmargin=0 rightmargin=0 onkeydown=body_onkeydown(event) onload=body_onload() scroll=auto>');
	document.write('<form>');
	document.write('<table border=0 cellpadding=0 cellspacing=8' + ((msLayout == 'T') ? ' align=center' : '') + '>');
	document.write(' <tr>');
	if (msLayout == 'L') 
	{
		document.write('  <td id=tdBox1 valign=top>');
		document.write('   <div align=center>');
		if (mbIE || !mbAll || (msAlbumTitle != '') || (msAlbumDescr != '') || (msAlbumDate  != '')) writeBoxOnLeft1();
		if (mbIE || !mbAll) writeBoxOnLeft2();
		if (mbDhtml && !mbHideKeyTips) writeKeyboardTips();
		document.write('   </div>');
		document.write('  </td>');
		document.write('  <td valign=top>');
		if (mbIE || mbAll) writeThumbnails();
		if (mbIE || !mbAll) writePhoto();
		writeFooter();
		document.write('  </td>');
	}
	else
	{
		document.write('  <td id=tdBox1 align=center>');
		writeBoxOnTop();
		document.write('  </td>');
		document.write(' </tr>');
		document.write(' <tr>');
		document.write('  <td align=center>');
		document.write('   <table border=0 cellpadding=0 cellspacing=0 align=center>');
		document.write('    <tr>');
		document.write('     <td>');
		if (mbIE || mbAll) writeThumbnails();
		if (mbIE || !mbAll) writePhoto();
		document.write('     </td>');
		document.write('    </tr>');
		document.write('    <tr>');
		document.write('     <td>');
		writeFooter();
		document.write('     </td>');
		document.write('    </tr>');
		document.write('   </table>');
		if (mbDhtml && !mbHideKeyTips) writeKeyboardTips();
		document.write('  </td>');
	}
	document.write('  </td>');
	document.write(' </tr>');
	document.write('</table>');
	document.write('</form>');
	document.write('</body>');
}

//-----------------

function writeBoxOnLeft1()
{
	document.write(msBorderBegin);
	document.write('<table border=0 cellpadding=0 cellspacing=10 width=160' + msTextBg + '>');
	if ((msAlbumTitle != '') || (msAlbumDescr != '') || (msAlbumDate != ''))
	{
		document.write(' <tr>');
		document.write('  <td align=center>');
		if (msAlbumTitle != '') document.write('<div align=center style="padding-bottom:2"><b><font face=arial,sans-serif>' + msAlbumTitle + '</font></b></div>');
		if (msAlbumDescr != '') document.write('<div align=center style="padding-top:3; padding-bottom:3"><small><font face=arial,sans-serif>' + msAlbumDescr + '</font></small></div>');
		if (msAlbumDate  != '') document.write('<div align=center style="padding-top:3; padding-bottom:3"><small><font face=arial,sans-serif>' + msAlbumDate + '</font></small></div>');
		document.write('  </td>');
		document.write(' </tr>');
	}
	document.write(' <tr>');
	document.write('  <td align=center>');
	if (mbIE || !mbAll || (mbDhtml && (mnTot > 2)))
	{
		document.write('   <table border=0 cellpadding=0 cellspacing=0>');
		document.write('    <tr>');
		if (mbIE || !mbAll)
		{
			document.write('<td align=center>');
			document.write(getButtonHtml('btnAll', msWord[0], 'showAll()', mbAll, -1, 'Index'));
			document.write('</td>');
		}
		if (mbDhtml && (mnTot > 2))
		{
			document.write('<td id=tdPlay style=padding-left:8' + (mbAll ? ';display:none' : '') + '>');
			document.write(getButtonHtml('btnAuto', getAutoCaption(), 'toggleAuto()', false, 1, (mbAuto ? 'Stop' : 'Play')) + '</td>');
			document.write('</td>');
		}
		document.write('    </tr>');
		document.write('   </table>');
	}
	if ((msSizes.length > 1) && (mbIE || !mbAll))
		document.write('   <table id=tblSize align=center border=0 cellpadding=0 cellspacing=0' + (mbAll ? ' style=display:none' : '') + '><tr><td colspan=2><img src=inc/p.gif height=8 width=1 vspace=0></td></tr><tr><td align=right valign=bottom><small><small><font face=arial,sans-serif>' + msWord[3] + '&nbsp;</font></small></small></td><td valign=bottom>' + getSizeOpts() + '</td></tr></table>');
	document.write('  </td>');
	document.write(' </tr>');
	document.write('</table>');
	document.write(msBorderEnd);
}

//------------------------

function writeBoxOnLeft2()
{
	if (mbIE) document.write('<span id=htmNav' + (!mbAll ? '' : ' style=display:none') + '>');

	if ((mnBorder == 0) && (msTextBg == ''))
		document.write('<table border=0 cellpadding=0 cellspacing=12 width=160><tr><td bgcolor=' + msBorderColor + '><img src=inc/p.gif height=1 width=1 vspace=0 hspace=0></td></tr></table>');
	else
		document.write('<img src=inc/p.gif height=8 width=1 vspace=0 hspace=0><br>');
	document.write(msBorderBegin);
	document.write('<table border=0 cellpadding=0 cellspacing=10 width=160' + msTextBg + '>');
	document.write(' <tr>');
	document.write('  <td align=right>' + getButtonHtml('btnPrev', msWord[4], 'goTo(mnPos-1)', false, -1, 'Prev') + '</td>');
	document.write('  <td align=left >' + getButtonHtml('btnNext', msWord[5], 'goTo(mnPos+1)', false, 1, 'Next') + '</td>');
	document.write(' </tr>');
	document.write(' <tr>');
	document.write('  <td colspan=2 align=center>');
	document.write('   <div align=center><small><font face=arial,sans-serif><span id=spnNum>' + (mnPos+1) + '</span> ' + msWord[6] + ' <img src=inc/p.gif width=2 height=1 hspace=0 vspace=0>' + mnTot + '</font></small></div>');
	document.write('   <div align=center id=divTitle style=padding-top:7' + ((msTitle[mnPos] == '') ? ';display:none' : '') + '><b><small><font face=arial,sans-serif><span id=spnTitle>' + msTitle[mnPos] + '</span></font></small></b></div>');
	document.write('   <div align=center id=divDescr style=padding-top:6' + ((msDescr[mnPos] == '') ? ';display:none' : '') + '><small><font face=arial,sans-serif><span id=spnDescr>' + msDescr[mnPos] + '</span></font></small></div>');
	document.write('  </td>');
	document.write(' </tr>');
	document.write(' <tr>');
	document.write('  <td align=right>' + getButtonHtml('btnFirst', msWord[7], 'goTo(0)',       false, -1, 'First') + '</td>');
	document.write('  <td align=left>'  + getButtonHtml('btnLast',  msWord[8], 'goTo(mnTot-1)', false,  1, 'Last') + '</td>');
	document.write(' </tr>');
	document.write('</table>');
	document.write(msBorderEnd);

	if (mbIE) document.write('</span>');
}

//-----------------

function writeBoxOnTop()
{
	document.write(msBorderBegin);
	var w = mnDim2;
	if (msTextBgColor != '')
	{
		w += 16;
		if (mnBorder == 3) w += 2;
	}
	document.write('<table border=0 cellpadding=0 cellspacing=6 width=' + w + msTextBg + '>');
	document.write(' <tr>');
	if (mbIE || !mbAll)
	{
		document.write('  <td align=left valign=middle>');
		document.write(getButtonHtml('btnAll', msWord[0], 'showAll()', mbAll, -1, 'Index'));
		document.write('  </td>');
	}
	document.write('  <td align=center valign=middle>');
	document.write('   <font face=arial,sans-serif>');
	if (msAlbumTitle != '') document.write('<b>' + msAlbumTitle + '</b>');
	if (msAlbumDescr != '') document.write(((msAlbumTitle != '') ? '<br>' : '') + '<small>' + msAlbumDescr + '</small>');
	if (msAlbumDate != '') document.write((((msAlbumTitle != '') || (msAlbumDescr != '')) ? '<br>' : '') + '<small>' + msAlbumDate + '</small>');
	document.write('   </font>');
	document.write('  </td>');
	if (((msSizes.length > 1) && (mbIE || !mbAll)) || (mbDhtml && (mnTot > 2)))
	{
		document.write('  <td align=right valign=middle nowrap>');
		document.write('   <table border=0 cellpadding=0 cellspacing=0>');
		document.write('    <tr>');
		if ((msSizes.length > 1) && (mbIE || !mbAll))
			document.write('<td><table id=tblSize border=0 cellpadding=0 cellspacing=0' + (mbAll ? ' style=display:none' : '') + '><tr><td align=right valign=bottom><small><small><font face=arial,sans-serif>' + msWord[3] + '&nbsp;</font></small></small></td><td valign=bottom>' + getSizeOpts() + '</td></tr></table></td>');
		if (mbDhtml && (mnTot > 2))
		{
			document.write('<td id=tdPlay style=padding-left:5' + (mbAll ? ';display:none' : '') + '>');
			document.write(getButtonHtml('btnAuto', getAutoCaption(), 'toggleAuto()', false, 1, (mbAuto ? 'Stop' : 'Play')));
			document.write('</td>');
		}
		document.write('    </tr>');
		document.write('   </table>');
		document.write('  </td>');
	}
	document.write(' </tr>');

	if (mbIE || !mbAll)
	{
		document.write(' <tr id=htmNavLine' + (mbAll ? ' style=display:none' : '') + '><td colspan=3 bgcolor=' + msBorderColor + '><img src=inc/p.gif width=1 height=1 hspace=0 vspace=0></td></tr>');
		document.write(' <tr id=htmNav' + (mbAll ? ' style=display:none' : '') + '>');
		document.write('  <td align=left valign=top>');
		document.write('   <table border=0 cellpadding=0 cellspacing=0>');
		document.write('    <tr>');
		document.write('     <td>' + getButtonHtml('btnFirst', msWord[7], 'goTo(0)',       false, -1, 'First') + '</td>');
		document.write('     <td><img src=inc/p.gif width=5 height=1 hspace=0 vspace=0></td>');
		document.write('     <td>' + getButtonHtml('btnPrev',  msWord[4], 'goTo(mnPos-1)', false, -1, 'Prev') + '</td>');
		document.write('    </tr>');
		document.write('   </table>');
		document.write('  </td>');
		document.write('  <td align=center valign=top>');
		document.write('   <small><font face=arial,sans-serif><span id=spnNum>' + (mnPos+1) + '</span> ' + msWord[6] + ' <img src=inc/p.gif width=2 height=1 hspace=0 vspace=0>' + mnTot + '</font></small>');
		document.write('   <span id=divTitle style=' + ((msTitle[mnPos] == '') ? 'display:none' : '') + '><small><font face=arial,sans-serif>:&nbsp;&nbsp;<b><span id=spnTitle>' + msTitle[mnPos] + '</span></b></font></small></span>');
		document.write('   <div id=divDescr style=' + ((msDescr[mnPos] == '') ? 'display:none' : '') + '><small><font face=arial,sans-serif><span id=spnDescr>' + msDescr[mnPos] + '</span></font></small></div>');
		document.write('  </td>');
		document.write('  <td align=right valign=top>');
		document.write('   <table border=0 cellpadding=0 cellspacing=0>');
		document.write('    <tr>');
		document.write('     <td>' + getButtonHtml('btnNext', msWord[5], 'goTo(mnPos+1)', false, 1, 'Next') + '</td>');
		document.write('     <td><img src=inc/p.gif width=5 height=1 hspace=0 vspace=0></td>');
		document.write('     <td>' + getButtonHtml('btnLast', msWord[8], 'goTo(mnTot-1)', false, 1, 'Last') + '</td>');
		document.write('    </tr>');
		document.write('   </table>');
		document.write('  </td>');
		document.write(' </tr>');
	}
	document.write('</table>');
	document.write(msBorderEnd);
}

//------------------------

function writeKeyboardTips()
{
	document.write('<span id=spnKeyTips' + ((mbAll || (msWord[9] == ''))? ' style=display:none' : '') + '>');
	document.write('<img src=inc/p.gif height=' + ((msLayout == 'T') ? '7' : '25') + ' width=1 vspace=0 hspace=0><br>');
	document.write('<table border=0 cellpadding=0 cellspacing=0 style="border:1px solid ' + msBgTextColor + '">')
	document.write(' <tr bgcolor=' + msBgTextColor + '>');
	document.write('  <td>');
	document.write('   <table border=0 cellpadding=1 cellspacing=0 width=100% style="color:' + msBgColor + ';font-family:arial,sans-serif">');
	document.write('    <tr>');
	document.write('     <td valign=middle><small><small>&nbsp;&nbsp;' + msWord[9] + '&nbsp;&nbsp;&nbsp;</small></small></td>');
	document.write('     <td valign=top align=right style="padding-top:2; padding-bottom:3; cursor:pointer"><span style="padding-left:2; padding-right:2; font-size:8; cursor:pointer; border:1px solid ' + msBgColor + '" onclick=hideKeyboardTips()>X</span></td>');
	document.write('    </tr>');
	document.write('   </table>');
	document.write('  </td>');
	document.write(' </tr>');
	document.write(' <tr>');
	document.write('  <td align=center>');
	document.write('   <table border=0 cellpadding=0 cellspacing=0 width=100% style="color:' + msBgTextColor + ';font-family:arial,sans-serif">');
	document.write('    <tr style=padding-top:2><td align=center><img src=inc/arrowRight.gif width=13 height=7 hspace=2 vspace=0></td><td><small><small>: ' + msWord[10] + '&nbsp;</small></small></td></tr>');
	document.write('    <tr><td align=center><img src=inc/arrowLeft.gif width=13 height=7 hspace=2 vspace=0></td><td><small><small>: ' + msWord[11] + '&nbsp;</small></small></td></tr>');
	document.write('    <tr id=trF11><td align=center><small><small>&nbsp;F11</small></small></td><td><small><small>: ' + msWord[12] + ' &nbsp;</small></small></td></tr>');
	if (mbIE && (mnTransition != 0))
	document.write('    <tr><td align=center><small><small>E</small></small></td><td><small><small>: ' + msWord[13] + ' <span id=spnTransOnOff>' + msWord[15] + '</span>&nbsp;</small></small></td></tr>');
	document.write('   </table>');
	document.write('  </td>');
	document.write(' </tr>');
	document.write('</table>');
	document.write('</span>');
}

//------------------------

function writePhoto()
{
	if (mbIE) document.write('<span id=spnPhoto' + (!mbAll ? '' : ' style=display:none') + '>');
	document.write(msBorderBegin);
	if (msTextBgColor != '') document.write('<table border=0 cellpadding=0 cellspacing=8' + msPhotoBg + '><tr><td bgcolor=000000>');
	document.write('<img id=img src="' + msSize + '/' + msImage[mnPos] + '.jpg" border=0 vspace=0 hspace=0' + (((mnBorder == 3) && (msTextBgColor != '')) ? ' style="border:1px solid ' + msBorderColor + '"': '') + '>');
	if (msTextBgColor != '') document.write('</td></tr></table>');
	document.write(msBorderEnd);
	if (mbIE) document.write('</span>');
}

//----------------------

function writeThumbnails()
{
	if (mbIE) document.write('<span id=spnThumbnails>');
	if (mbAll) document.write(getThumbnailsHtml());
	if (mbIE) document.write('</span>');
}

//----------------------

function writeFooter()
{
	document.write('<table id=tblFooter border=0 cellpadding=0 cellspacing=2 width=100%>');
	document.write(' <tr>');
	if (mbHome)
	{
		document.write('  <td align=left><small><small><font face=arial,sans-serif color=' + msBgTextColor + '>&nbsp;');
		document.write('<a href="');
		var sUrl;
		var s = msHomeURL.toLowerCase();
		if ((s.indexOf('/') == 0) || (s.indexOf('http://') == 0) || (s.indexOf('https://') == 0))
			sURL = msHomeURL;
		else
		{
			sUrl = location.href;
			sUrl = sUrl.substring(0, sUrl.lastIndexOf('/'));
			s = msHomeURL;
			while (s.indexOf('../') == 0)
			{
				sUrl = sUrl.substring(0, sUrl.lastIndexOf('/'));
				if (s.length == 3) s = '';
				else s = s.substring(3);
			}
			sUrl += '/' + s;
		}			
		if (location.href.substring(0, 4).toLowerCase() != 'http')
			document.write('javascript:alert(\'This link works only when the album is viewed on the web.\')');
		else
			document.write(sUrl);
		document.write('">' + msHomeCaption + '</a>');
		document.write('</font></small></small></td>');
	}
	document.write('  <td align=right valign=middle><small><small><font face=arial,sans-serif color=' + msBgTextColor + '><a href="http://www.s10soft.com/">S10 Software</a>&nbsp;</font></small></small></td>');
	document.write(' </tr>');
	document.write('</table>');
}

//----------------------

function getButtonHtml(sId, sText, sOnclick, bHide, nImgPos, sImg)
{
	sText = getButtonCaption(sText, nImgPos, sImg);
	if (mbDhtml) return '<div id=' + sId + ' align=center style="width:64; height:22; background-image:url(inc/button1.gif); font-family:arial,sans-serif; font-size:' + mnBtnTextSize + 'pt; color:' + msButtonTextColor + '; cursor:pointer" onmouseover="this.style.backgroundImage=\'url(inc/button2.gif)\'" onmouseout="this.style.backgroundImage=\'url(inc/button1.gif)\'" onmousedown="if (event.button!=2) {this.childNodes[0].width=3; this.childNodes[0].height=16; if (mbIE) this.style.backgroundImage=\'url(inc/button1.gif)\';}" onmouseup="if (event.button!=2) {this.childNodes[0].width=1; this.childNodes[0].height=15; if (mbIE) this.style.backgroundImage=\'url(inc/button2.gif)\'}" onclick="' + sOnclick + '"' + (bHide ? ' style=display:none' : '') + '>' + sText + '</div>';
	return '<input type=button onclick="' + sOnclick + '" value="' + sText + '"' + (bHide ? ' style=display:none' : '') + '>';
}

//----------------------

function getButtonCaption(sText, nImgPos, sImg)
{
	if (!mbDhtml)
	{
		if ((sImg == 'Prev') || (sImg == 'First')) return ('&lt;&nbsp;' + sText);
		if ((sImg == 'Next') || (sImg == 'Last')) return (sText + '&nbsp;&gt;');
		return sText;
	}
	var s = ((nImgPos == 0) ? '' : '<img src=inc/control' + sImg + '.gif width=15 height=' + (sImg == 'Index' ? 8 : 7) + ' hspace=0 vspace=0>');
	if (sImg == 'Stop') s += '<img id=imgStopBar src=inc/p.gif style="position:relative; top:-1; left:-8; width:1; height:5; visibility:hidden; background:#ffffff">';
	s = ((nImgPos == -1) ? s + sText : sText + s);
	s = '<img src=inc/p.gif width=1 height=15 hspace=0 vspace=0>' + s;
	return s;
}

//----------------------

function getThumbnailsHtml()
{
	var sHtml = msBorderBegin;
	sHtml += '<table border=0 cellpadding=0 cellspacing=0' + msPhotoBg + '>';
	sHtml += '<tr>';
	sHtml += '<td align=center>';
	sHtml += '<table border=0 cellpadding=0 cellspacing=8>';

	var nCols;
	if (mnColumns > 0) nCols = mnColumns;
	else nCols = 5;
	var nHeight;
	var nMaxHeight = 0;
	var i;
	var n = 0;
	while (n < mnTot)
	{
		sHtml += '<tr>';
		//scan ahead and find tallest thumbnail in row:
		nMaxHeight = 0;
		for (i = 0; i < nCols; i++)
			if ((n + i) < mnTot)
			{
				nHeight = mnThumH[n + i];
				if (nHeight > nMaxHeight) nMaxHeight = nHeight;
			}
		//generate one row:
		for (i = 0; i < nCols; i++)
		{
			sHtml += '<td align=center valign=top width=' + mnDim0 + '>';
			if (n < mnTot)
			{
				if (mnThumH[n] < nMaxHeight)
					sHtml += '<img src=inc/p.gif height=' + (nMaxHeight - mnThumH[n]) + ' width=1><br>';
				sHtml += '<a href=javascript:goTo(' + n + ')>';
				sHtml += '<img src="T/' + msImage[n] + '.jpg" height=' + mnThumH[n] + ' width=' + mnThumW[n] + ' border=0 hspace=0 vspace=0 title="' + stripTags(msDescr[n]) + '" style="border:1px solid ' + msBorderColor + '" onmouseover="this.style.borderColor=\'' + msTextColor + '\'" onmouseout="this.style.borderColor=\'' + msBorderColor + '\'">';
				sHtml += '</a>';
				if (msTitle[n] != '')
					sHtml += '<br><font face=arial,sans-serif><small><small>' + msTitle[n] + '</small></small></font>';
			}
			else sHtml += '&nbsp;';
			sHtml += '</td>';
			n++;
		}
		sHtml += '</tr>';
	}

	sHtml += '</table>';
	sHtml += '</td>';
	sHtml += '</tr>';
	sHtml += '</table>';
	sHtml += msBorderEnd;

	return sHtml;
}

//------------------------

function getSizeOpts()
{
	var sHtml = '';
	if (msSizes.charAt(0) == 'S') sHtml += getSizeOpt('S', 9);
	sHtml += getSizeOpt('M', 11);
	if (msSizes.charAt(msSizes.length - 1) == 'L') sHtml += getSizeOpt('L', 13);
	return sHtml;
}

//------------------------

function getSizeOpt(sSize, nPix)
{
	var sHtml = '';
	if (!mbDhtml) sHtml = '<a href="javascript:setSize(\'' + sSize + '\')">';
	sHtml += '<img vspace=2 border=0 id=imgSize' + sSize + ' height=' + nPix + ' width=' + nPix + ' hspace=1';
	sHtml += ' src=inc/size' + ((sSize == msSize) ? 'X' : '1') + '.gif';
	if (mbDhtml)
	{
		if (msSize != sSize) sHtml += ' style=cursor:pointer';
		sHtml += ' onclick="setSize(\'' + sSize + '\')"';
		sHtml += ' onmouseover="if (msSize != \'' + sSize + '\') this.src = \'inc/size2.gif\'"';
		sHtml += ' onmouseout="if (msSize != \'' + sSize + '\') this.src = \'inc/size1.gif\'">';
	}
	else
		sHtml += '></a>';
	return sHtml;
}

//-----------------

function goTo(nPos, bPreloaded)
{
	if (nPos < 0) nPos = mnTot - 1;
	else if (nPos >= mnTot)
		nPos = 0;

	if (!mbIE || bPreloaded)
	{
		mnPrevPos = mnPos;
		mnPos = nPos;
	}

	if (mbIE)
	{
		if (!bPreloaded)
		{
			document.body.style.cursor = 'wait';
			mnNextPos = nPos;
			moNextImg.src = msSize + '/' + msImage[nPos] + '.jpg';
			return;
		}
		document.body.style.cursor = 'default';
		document.all.spnNum.innerText = (nPos + 1);
		document.all.spnTitle.innerHTML = msTitle[nPos];
		document.all.divTitle.style.display = ((msTitle[nPos] == '') ? 'none' : '');
		document.all.spnDescr.innerHTML = msDescr[nPos];
		document.all.divDescr.style.display = ((msDescr[nPos] == '') ? 'none' : '');
		if (!mbAll && (mnCurTransition != 0))
		{
			if (mnCurTransition == 1) setTransition(4);
			else if (mnCurTransition == 2) setTransition((mnPos > mnPrevPos) ? 'Forward' : 'Reverse');
			else setTransition(null);
			try {document.all.img.filters.item(0).Apply();}
			catch(e) {}
		}
		document.all.img.src = msSize + '/' + msImage[nPos] + '.jpg';
		if (!mbAll && (mnCurTransition != 0))
			try {document.all.img.filters.item(0).Play();}
			catch(e) {}
		if (mbAll)
		{
			document.all.spnThumbnails.style.display = 'none';
			document.all.tdBox1.style.display = '';
			document.all.btnAll.style.display = '';
			if (mnTot > 2) document.all.tdPlay.style.display = '';
			if (msSizes.length > 1) document.all.tblSize.style.display = '';
			if (msLayout == 'T') document.all.htmNavLine.style.display = '';
			document.all.htmNav.style.display = '';
			if (msWord[9] != '') document.all.spnKeyTips.style.display = '';
			document.all.spnPhoto.style.display = '';
			mbAll = false;
		}
		if (mbAuto)
			if (nPos == (mnTot - 1)) toggleAuto();
			else
			{
				mnProgress = 0;
				document.getElementById('imgStopBar').style.visibility = 'hidden';
				document.getElementById('imgStopBar').style.left = -8;
				if (!mbTimerRunning) startTimer();
			}
	}
	setLocation();
}

//-----------------

function showAll()
{
	if (mbAuto && mbOpera)
	{
		toggleAuto();
		return;
	}
	if (mbIE)
	{
		if (mbAuto) toggleAuto();
		if (document.all.spnThumbnails.innerHTML == '')
			document.all.spnThumbnails.innerHTML = getThumbnailsHtml();
		if ((msAlbumTitle == '') && (msAlbumDescr == '') && (msAlbumDate == '')) document.all.tdBox1.style.display = 'none';
		document.all.btnAll.style.display = 'none';
		if (mnTot > 2) document.all.tdPlay.style.display = 'none';
		if (msSizes.length > 1) document.all.tblSize.style.display = 'none';
		if (msLayout == 'T') document.all.htmNavLine.style.display = 'none';
		document.all.htmNav.style.display = 'none';
		document.all.spnKeyTips.style.display = 'none';
		document.all.spnPhoto.style.display = 'none';
		document.all.spnThumbnails.style.display = '';
		mbAll = true;
	}
	mnPrevPos = mnPos;
	mnPos = -1;	
	setLocation();
}

//-----------------

function setSize(sSize)
{
	if (msSize == sSize) return;
	if (mbIE)
	{
		document.all('imgSize' + msSize).src = 'inc/size1.gif';
		document.all('imgSize' + msSize).style.cursor = 'pointer';
	}
 	msSize = sSize;
	if (mbIE)
	{
		document.all('imgSize' + msSize).src = 'inc/sizeX.gif';
		document.all('imgSize' + msSize).style.cursor = '';
		document.all('img').src = sSize + '/' + msImage[mnPos] + '.jpg';
	}
	else setLocation();
}

//-----------------

function setLocation()
{
	var sUrl = 'index.htm' + (mbIE ? '#' : '?') + (mnPos + 1);
	if (!mbIE)
	{
		sUrl += '_' + msSize;
		if (mbAuto || mbHideKeyTips) sUrl += '_' + ((mbAuto && (mnPos != -1)) ? 'A' : '') + (mbHideKeyTips ? '_' : '');
		mnPos = mnPrevPos;
		mnPrevPos = -1;
	}
	location = sUrl;
}

//-----------------

function toggleAuto()
{
	mbAuto = !mbAuto;
	mnProgress = 0;
	if (mbIE) document.all.btnAuto.innerHTML = getButtonCaption(getAutoCaption(), 1, (mbAuto ? 'Stop' : 'Play'));
	if (mbAuto) goTo((mnPos == (mnTot - 1)) ? 0 : (mnPos + 1));
	else if (!mbIE) setLocation();
}

//-----------------

function startTimer()
{
	mbTimerRunning = true;
	setTimeout('endTimer()', Math.floor(mnInterval * 1000 / 6));
}

//-----------------

function endTimer()
{
	mbTimerRunning = false;
	if (!mbAuto) return;
	if (++mnProgress == 6)
	{
		if (!mbIE && (mnPos == (mnTot - 2)))
			mbAuto = false;
		document.getElementById('imgStopBar').style.visibility = 'hidden';
		goTo(mnPos + 1);
	}
	else
	{
		if (mnProgress == 1) document.getElementById('imgStopBar').style.visibility = 'visible';
		else document.getElementById('imgStopBar').style.left = mnProgress - 9;
		startTimer();
	}
}

//-----------------

function onNextImgLoad()
{
	goTo(mnNextPos, true);
}

//-----------------

function getAutoCaption()
{
	return (mbAuto ? msWord[2] : msWord[1]);
}

//-----------------

function setTransition(n)
{
	if (n == null) n = Math.floor(Math.random() * msTrans.length);
	var sProps = msTrans[n].split(',');
	var sFilt = 'progid:DXImageTransform.Microsoft.' + sProps[0] + '(Duration=1';
	var sProp, sNameVal, sVals;
	for(var n = 1; n < sProps.length; n++)
	{
		sProp = sProps[n];
		if (sProp.indexOf('/') != -1)
		{
			sNameVal = sProp.split('=');
			sVals = sNameVal[1].split('/');
			sProp = sNameVal[0] + '=' + sVals[Math.floor(Math.random() * sVals.length)];
		}
		sFilt += ',' + sProp;
	}
	sFilt += ')';
	document.all.img.style.filter = sFilt;
}

//-----------------

function hideKeyboardTips()
{
	if (mbIE) document.all.spnKeyTips.innerHTML = '';
	else
	{
		mbHideKeyTips = true;
		setLocation();
	}
}

//-----------------

function stripTags(html)
{
	var n1 = html.indexOf('<');
	if (n1 == -1) return html;
	var n2 = html.indexOf('>');
	if (n2 < n1) return html;
	var sText = (n1 == 0) ? '' : html.substring(0, n1);
	if (n2 == (html.length - 1)) return sText;
	return sText + stripTags(html.substring(n2 + 1));
}

//-----------------

function body_onkeydown(e)
{
	if (e == null) return;
	if (e.keyCode == 27)  //ESC
	{
		if (moHta != null) moHta.close();
		return;
	}
	if (mbAll) return;
	if (e.keyCode == 37)  //LeftArrow
	{
		goTo(mnPos - 1);
		e.returnValue = false;
		return;
	}
	if (e.keyCode == 39)  //RightArrow
	{
		goTo(mnPos + 1);
		e.returnValue = false;
		return;
	}
	if (!mbIE) return;
	if (e.keyCode == 88)  //X
	{
		document.all.spnKeyTips.innerHTML = '';
		return;
	}
	if (e.keyCode == 69)  //E
	{
		if (mnTransition == 0) return;
		mnCurTransition = mnTransition - mnCurTransition;
		if (document.all.spnTransOnOff) document.all.spnTransOnOff.innerHTML = msWord[(mnCurTransition == 0) ? 14 : 15];
	}
}

//-----------------

function body_onload()
{
	if (mbIE) focus();
	else if (mbAuto) startTimer();
}

//-----------------

function setHta(oHta)
{
	moHta = oHta;
	mbHideKeyTips = true;
	document.all.tblFooter.style.display = 'none';
	hideKeyboardTips();
	document.all.spnKeyTips.insertAdjacentHTML('BeforeBegin', '<div style="padding-top:5;font-family:arial,sans-serif"><small><b><a href="javascript:moHta.close()">Exit</a></b></div>');
	if ((mnDim3 > 0) && (screen.width > (mnDim3 + 220))) setSize('L');
}
