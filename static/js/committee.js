$(document).ready(function() {
  $("#tabs .item").tab({history:true, historyType: 'hash'});
  filter('meplist');
  filter('dossierlist');
});
