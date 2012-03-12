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

$(document).ready(function() {
  $('.button').click(function() {
   $(this).next().toggleClass('hidden');
  });
  if(getCookie('epheader')) {
   $('.epheader').toggleClass('hidden');
  }
  $('#toggle_ep').click(function() {
   $('.epheader').toggleClass('hidden');
   if(getCookie('epheader')) {
     deleteCookie('epheader');
   } else {
     setCookie('epheader','on');
   }
  });
  $( "#tabs" ).tabs();
  $('#notif_form').submit(function() {
      var group = $(this).find('div').children('input:eq(1)').attr('value');
       if(!group) {
           $.ajax({url: '/notification', success: function(data) { group = data;
               $.ajax({url: group, success: function(data) {
                   $.ajax({url: group+'/add/emails/'+$('#notif_form div').children('input:first').attr('value'), success: function(data) { $('#notif_subscr h3').html(data); }});
                   $.ajax({url: group+'/add/dossiers/'+$('#content > h2:first').html()});
               }});
           }});
       } else {
       $.ajax({url: '/notification/'+group, success: function(data) {
           $.ajax({url: '/notification/'+group+'/add/emails/'+$('#notif_form div').children('input:first').attr('value')});
           $.ajax({url: '/notification/'+group+'/add/dossiers/'+$('#content > h2:first').html(), success: function(data) {
               $('#notif_subscr h3').html(data);
               }});
           }});
       }
       return false;
  });
});
