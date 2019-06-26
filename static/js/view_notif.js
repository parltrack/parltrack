var submit = function() {
   var group_id = $('#group_id').val()
   $.ajax({url: group_id, success: function(data) {
      $.ajax({url: group_id+'/add/emails/'+$('#notif_form div').children('input:first').attr('value'), success: function(data) { $('#notif_subscr h3').html(data); }});
      $.ajax({url: group_id+'/add/dossiers/'+$('#content > h2:first').html()});
   }
 });
 return false;
}

$(document).ready(function() {
  $('#unsubscribe_link').click(function() {
     $('.modal').modal('show');
  });
  $('#submit').click(function() {
      submit();
  });
  $('#notif_form').submit(submit());
  $('#hide').click(function() {
    $('.modal').modal('hide');
  });
});
