// designed by sahua   ::)
//           20/03/2001   ::)

function cur_sign() { 
num=document.sign.nmb.selectedIndex; 
if(num==1)  { nm="you"; fld="africa/" }
if(num==2)  { nm="ali"; fld="mali/" }
if(num==3)  { nm="oumou"; fld="mali/" }
if(num==4)  { nm="khaled"; fld="east/" }
if(num==5)  { nm="perry"; fld="latin/" }
if(num==6)  { nm="salif"; fld="mali/" }
if(num==7)  { nm="boine"; fld="europe/" }
if(num==8)  { nm="evora"; fld="latin/" }
if(num==9)  { nm="bvsc"; fld="latin/" }
if(num==10)  { nm="djivan"; fld="russiaround/" }
if(num==11) { nm="inti"; fld="latin/" }
if(num==12) { nm="oryema"; fld="africa/" }
if(num==13) { nm="vari"; fld=""}
if(num==14) { nm="makeba"; fld="africa/" }
if(num==15) { nm="baobab"; fld="africa/" }
if(num==16) { nm="wemba"; fld="africa/" }
if(num==17) { nm="tuva"; fld="russiaround/" }
if(num==18) { nm="kar"; fld="mali/" }
if(num==19) { nm="marta"; fld="europe/" }
if(num==20) { nm="kante"; fld="africa/" }
if(num==21) { nm="baca"; fld="latin/" }
if(num==22) { nm="mahmed"; fld="east/" }
if(num==23) { nm="japan"; fld="asia/" }
if(num==24) { nm="mapfumo"; fld="africa/" }
if(num==25) { nm="toumani"; fld="mali/" }
if(num==26) { nm="sona"; fld="africa/" }
if(num==27) { nm="uz"; fld="russiaround/" }
if(num==28) { nm="alim"; fld="russiaround/" }
if(num==29) { nm="rokia"; fld="mali/" }
if(num==30) { nm="vietnam"; fld="asia/" }
if(num==31) { nm="starostin"; fld="russiaround/" }

parent.content.location=fld+nm+"_cont.html"; 
parent.menu.location=fld+nm+"_navi.html";
parent.header.document.topname.src ="../Pictures/"+nm+"/"+nm+"_top.gif";
parent.header.document.date.src ="../Pictures/"+nm+"/"+nm+"_0.gif";
}

function chTop() {
adr1 = parent.menu.location.href;
sec1=adr1.lastIndexOf("_");
fir1=adr1.lastIndexOf("/")+1;
adr2 = parent.header.document.topname.src;
sec2=adr2.lastIndexOf("_");
fir2=adr2.lastIndexOf("/")+1; 
curname = adr1.substring(fir1,sec1);
	if(curname!=adr2.substring(fir2,sec2)) {
		parent.header.document.topname.src ="../Pictures/"+curname+"/"+curname+"_top.gif";
		parent.header.document.date.src ="../Pictures/"+curname+"/"+curname+"_0.gif";
		parent.content.location=fld+curname+"_cont.html";
	}
}

function reFrm(f) {
	f.reset(); f.nmb.blur(); window.focus();
}