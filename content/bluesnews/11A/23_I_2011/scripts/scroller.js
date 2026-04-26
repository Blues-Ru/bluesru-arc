var tdStart;
var divPager;
var pagerWidth;
var tableThumb;
var tableThumbLeft;
var tableThumbLeftNew;
var forwardBtn;
var backBtn;
var tableFirstChild;
var tableLastChild;
var Timer;

function disableForwardBtn(){
	forwardBtn.className = "pagerButtonDisabled";
	MM_swapImage('lastSlide','images/last_slide1.png','images/last_slide.png',1);
}
function disableBackBtn(){
	backBtn.className = "pagerButtonDisabled";
	MM_swapImage('firstSlide','images/first_slide1.png','images/first_slide.png',1);
}
function enableForwardBtn(){
	forwardBtn.className = "pagerButtonEnabled";
	MM_swapImage('lastSlide','images/last_slide.png','images/last_slide1.png',1);
}
function enableBackBtn(){
	backBtn.className = "pagerButtonEnabled";
	MM_swapImage('firstSlide','images/first_slide.png','images/first_slide1.png',1);
}

function tableCheckLeft(){
	if (tableThumbLeftNew >= 0){
		tableThumbLeftNew = 0;
		disableBackBtn();
		tdStart = tableFirstChild;
	} else {
		enableBackBtn();
	}
}
function tableCheckRight(){
	tableThumbRight = tableThumbLeftNew + tableThumb.offsetWidth;
	if (tableThumbRight <= pagerWidth){
		tableThumbLeftNew +=  pagerWidth - tableThumbRight;
		disableForwardBtn();
		tdStart = tableLastChild;
	} else {
		enableForwardBtn();
	}
}

function thumbPagerInit(){
	tdStart = document.getElementById('td_current');
	divPager = document.getElementById('thumbPagerContainer');
	pagerWidth = divPager.offsetWidth;
	tableThumb = document.getElementById('tableThumbPager');
	forwardBtn = document.getElementById('forwardButton');
	backBtn = document.getElementById('backButton');
	tableFirstChild = tableThumb.rows[0].cells[0];
	tableLastChild = tableThumb.rows[0].cells[tableThumb.rows[0].cells.length-1];
	var curTdLeft = tdStart.offsetLeft;
	var curTdWidth = tdStart.offsetWidth;
	if (tdStart == tableFirstChild) {
		tableThumbLeft = 0;
		disableBackBtn();
	}
	else if (tdStart == tableLastChild) {
		tableThumbLeft = pagerWidth - tableThumb.offsetWidth;
		disableForwardBtn();
	}
	else {
		tableThumbLeft = pagerWidth/2-curTdLeft-curTdWidth/2;
	}
	tableThumbLeftNew = tableThumbLeft;
	tableCheckRight();
	tableCheckLeft();
	divPager.scrollLeft = - tableThumbLeftNew;
}

function pagerScrollLeft() {
	if(tableThumbLeft < tableThumbLeftNew) {
		tableThumbLeft += 30;
		if (tableThumbLeft > tableThumbLeftNew) {
			tableThumbLeft = tableThumbLeftNew;
		}
		divPager.scrollLeft =  - tableThumbLeft;
	} else {
		clearInterval(Timer);
	}
}
function pagerScrollRight() {
	if(tableThumbLeft > tableThumbLeftNew) {
		tableThumbLeft -= 30;
		if (tableThumbLeft < tableThumbLeftNew) {
			tableThumbLeft = tableThumbLeftNew;
		}
		divPager.scrollLeft =  - tableThumbLeft;
	} else {
		clearInterval(Timer);
	}
}

function scrollBack(){
	if (tdStart == tableFirstChild) return;
	tableThumbLeft = tableThumbLeftNew;
	if (tableThumbLeft == 0) return;
	tdFound = false;
	clearInterval(Timer);
	tdStartLeft = tdStart.offsetLeft - Math.abs(tableThumbLeft);
	if (tdStartLeft == 0) {
		tdFound = true;
		tdStart = tdStart.previousSibling;
	}
	while(!tdFound){
		if (tdStart.previousSibling) {
			tdSibling = tdStart.previousSibling;
		}
		else break;
		tdSiblingLeft = tdSibling.offsetLeft - Math.abs(tableThumbLeft);
		tdSiblingRight = tdSiblingLeft + tdSibling.offsetWidth;
		if ( ((tdSiblingLeft < 0)&&(tdSiblingRight > 0)) || ((tdSiblingRight <= 0)&&(tdStartLeft > 0)) ) {
			tdFound = true;
			tdStart = tdSibling;
		} else if(tdSiblingLeft == 0) {
			tdFound = true;
			tdStart = tdSibling.previousSibling;
		} else {
			tdStart = tdSibling;		
		}
	}
	tdStartLeft = tdStart.offsetLeft - Math.abs(tableThumbLeft);
	tdStartRight = tdStartLeft + tdStart.offsetWidth;
	tableThumbLeftNew = tableThumbLeft + pagerWidth - tdStartRight;
	tableCheckLeft();
	tableCheckRight();
	Timer = setInterval("pagerScrollLeft()", 1);
}

function scrollForward(){
	if (tdStart == tableLastChild) return;
	tableThumbLeft = tableThumbLeftNew;
	tableThumbRight = tableThumbLeft + tableThumb.offsetWidth;
	if (tableThumbRight <= pagerWidth) return; 
	tdFound = false;
	clearInterval(Timer);
	tdStartRight = tdStart.offsetLeft - Math.abs(tableThumbLeft) + tdStart.offsetWidth;
	if (tdStartRight == pagerWidth) {
		tdFound = true;
		tdStart = tdStart.nextSibling;
	}
	while(!tdFound){
		if (tdStart.nextSibling) {
			tdSibling = tdStart.nextSibling;
		}
		else break;
		tdSiblingLeft = tdSibling.offsetLeft - Math.abs(tableThumbLeft);
		tdSiblingRight = tdSiblingLeft + tdSibling.offsetWidth;
		if ( ((tdSiblingLeft < pagerWidth)&&(tdSiblingRight > pagerWidth)) || ((tdSiblingLeft >= pagerWidth)&&(tdStartRight < pagerWidth)) ) {
			tdFound = true;
			tdStart = tdSibling;
		} else if(tdSiblingRight == pagerWidth) {
			tdFound = true;
			tdStart = tdSibling.nextSibling;
		} else {
			tdStart = tdSibling;		
		}
	}
	tdStartLeft = tdStart.offsetLeft - Math.abs(tableThumbLeft);
	tableThumbLeftNew = tableThumbLeft - tdStartLeft;
	tableCheckRight();
	tableCheckLeft();
	Timer = setInterval("pagerScrollRight()", 1);
}