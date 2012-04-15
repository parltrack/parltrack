function getCookie(name) {
    var nameEQ = name + "=";
    var ca = document.cookie.split(';');
    for(var i=0;i < ca.length;i++) {
        var c = ca[i];
        while (c.charAt(0)==' ') c = c.substring(1,c.length);
        if (c.indexOf(nameEQ) == 0) return c.substring(nameEQ.length,c.length);
    }
    return null;
}
function deleteCookie(name) {
    setCookie(name,"",-1);
}
function setCookie(name,value,days) {
    if (days) {
        var date = new Date();
        date.setTime(date.getTime()+(days*24*60*60*1000));
        var expires = "; expires="+date.toGMTString();
    }
    else var expires = "";
    document.cookie = name+"="+value+expires+"; path=/";
}

function saved(node) {
  node.next('.saved').removeClass('hidden');
  node.next('.saved').show();
  node.next('.saved').fadeOut(4000);
}

$(document).ready(function() {
  $('.toggle').click(function() {
   var attrib=$(this).attr('id');
   if(getCookie(attrib)) {
     deleteCookie(attrib);
   } else {
     setCookie(attrib,'on');
   }
   saved($(this));
  });
  $('.edit').focusout(function() {
   setCookie($(this).attr('id'),$(this).attr('value'));
   saved($(this));
  });
});
