var subscribe = function() {
  var group = $('#group_name').val();
  var subject = $('#subject_name').val();
  if(!group) {
      $.ajax({url: '/notification', success: function(data) { group = data;
          $.ajax({url: group, success: function(data) {
              $.ajax({url: group+'/add/subjects/'+subject});
          }});
      }});
  } else {
  $.ajax({url: '/notification/'+group, success: function(data) {
      $.ajax({url: '/notification/'+group+'/add/subject/'+subject, success: function(data) {
          $('#notif_subscr h3').html(data);
          }});
      }});
  }
  $('.modal').modal('hide');
  return false;
}

$(document).ready(function() {
  $('.modal').modal('hide');
  $('#hide').click(function() {
      $('.modal').modal('hide');
  });
  $('#subscribe_link').click(subscribe);
  $('.subscribe').click(function() {
     console.log('asdf');
     var val = $(this).data('name');
     $('#subject_name').val(val);
     $('.modal').modal('show');
  });
});
