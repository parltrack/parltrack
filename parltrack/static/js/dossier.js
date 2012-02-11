$(document).ready(function() {
  $('.has_summary').click(function() {
   $(this).next('div').toggleClass('hidden');
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
