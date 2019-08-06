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
  //$('.popup').popup({hoverable:true, lastResort: true});
  $("#tabs .item").tab({history:true, historyType: 'hash'});
  $('.ui.accordion').accordion({
      clearable: true,
      placeholder: 'any'
  }) ;
  $('.ui.progress') .progress({
     duration : 100,
     total    : 100,
  });
  $('.ui.dropdown').dropdown();
  $('.button').click(function() {
   $(this).next().toggleClass('hidden');
  });
  var mail=getCookie('email');
  if(mail) {
    $('#emailinput').attr('value',mail);
  }
  $('#notif_form').submit(function() {
      var group = $('#groupinput').val();
      var email = $('#emailinput').val();
      var dossier = $('#dossier_ref').html();
      //console.log(email, dossier, group);
      if(!group) {
          $.ajax({url: '/notification', success: function(data) { group = data;
              $.ajax({url: group, success: function(data) {
                  $.ajax({url: group+'/add/emails/'+email, success: function(data) { $('#notif_subscr h3').html(data); }});
                  $.ajax({url: group+'/add/dossiers/'+dossier});
              }});
          }});
      } else {
      $.ajax({url: '/notification/'+group, success: function(data) {
          $.ajax({url: '/notification/'+group+'/add/emails/'+email});
          $.ajax({url: '/notification/'+group+'/add/dossiers/'+dossier, success: function(data) {
              $('#notif_subscr h3').html(data);
              }});
          }});
      }
      return false;
  });
});
