// frame structure generator
// designed by sahua 
// 6/7/1999 
//last modified 7/7/2001

function frame(anch,letter,num) {

if(letter=="s") {
    tmp="../inst/";
    filename="strum_"+anch.substring(0,1)+".html#"+anch;
    }
    else if(letter=="g") { 
          tmp="../styles/";
          filename="gloss_"+anch.substring(0,1)+".html#"+anch;
    }
    parent.header.location.href=tmp+"top.html";
    parent.menu.location.href=tmp+"navi.html";
    document.links[num].href=tmp+filename; 
}


        
        
                 
                 
        

