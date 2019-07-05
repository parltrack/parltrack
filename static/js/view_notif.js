var submit = function() {
   var group_id = $('#group_id').val()
   $.ajax({url: group_id, success: function(data) {
      if($('#email_name').val()) $.ajax({url: group_id+'/del/emails/'+$('#email_name').val()});
      if($('#dossier_name').val()) $.ajax({url: group_id+'/del/dossiers/'+$('#dossier_name').val()});
      if($('#subject_name').val()) $.ajax({url: group_id+'/del/subjects/'+$('#subject_name').val()});
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
  $('#notif_form').submit(submit);
  $('#hide').click(function() {
    $('.modal').modal('hide');
  });
});
