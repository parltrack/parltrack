$(document).ready(function() {
  $("#tabs .item").tab({history:true, historyType: 'hash'});
  $('.ui.accordion').accordion({
      clearable: true,
      placeholder: 'any'
  }) ;
  $('.ui.dropdown').dropdown();
});
