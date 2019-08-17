var unsubscribe = function() {
   var group_id = $('#group_id').val();
   $.ajax({url: group_id, success: function(data) {
      if($('#email_name').val()) $.ajax({url: group_id+'/del/emails/'+$('#email_name').val()});
      if($('#dossier_name').val()) $.ajax({url: group_id+'/del/dossiers/'+$('#dossier_name').val()});
      if($('#subject_name').val()) $.ajax({url: group_id+'/del/subjects/'+$('#subject_name').val()});
   }
 });
 return false;
};
var show_message = function(error) {
   var id = '#subscribe-message';
   if(error=='error') {
      id = '#subscribe-error';
   }
   $(id).show();
   setTimeout(function() {
      $(id).hide();
   }, 5000);
};
var submit_email = function() {
   var group_id = $('#group_id').val();
   var email = $('#subscribe-email').val();
   if(email) {
      $.ajax({url: group_id+'/add/emails/'+email, success: show_message, error: function() {show_message('error')}});
   }
   $('#subscribe_email').val('');
   return false;
};
var submit_meps_by_country = function() {
   var group_id = $('#group_id').val();
   var email = $('#subscribe-meps-by-country').val();
   if(email) {
      $.ajax({url: group_id+'/add/meps_by_country/'+email, success: show_message, error: function() {show_message('error')}});
   }
   return false;
};
var submit_meps_by_committee = function() {
   var group_id = $('#group_id').val();
   var email = $('#subscribe-meps-by-committee').val();
   if(email) {
      $.ajax({url: group_id+'/add/meps_by_committee/'+email, success: show_message, error: function() {show_message('error')}});
   }
   return false;
};
var submit_meps_by_group = function() {
   var group_id = $('#group_id').val();
   var email = $('#subscribe-meps-by-group').val();
   if(email) {
      $.ajax({url: group_id+'/add/meps_by_group/'+email, success: show_message, error: function() {show_message('error')}});
   }
   return false;
};

$(document).ready(function() {
  $('#unsubscribe_link').click(function() {
     $('.modal').modal('show');
  });
  $('#hide').click(function() {
    $('.modal').modal('hide');
  });
  $('#submit').click(unsubscribe);
  $('#notif_form').submit(unsubscribe);
  $('#subscribe-meps-by-country-button').click(submit_meps_by_country);
  $('#subscribe-meps-by-committee-button').click(submit_meps_by_committee);
  $('#subscribe-meps-by-group-button').click(submit_meps_by_group);
  $('#subscribe-email-button').click(submit_email);
  $('.ui.dropdown').dropdown({clearable: true});
});
