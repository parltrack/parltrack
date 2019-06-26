$(document).ready(function () {
  // Initialise Plugin
  $('#dossiers').tableFilter({
    columnFilters: [     
       { columnName: 'reference', inputType: 'empty', includeData: false},
       { columnName: 'title', inputType: 'empty'},
       { columnName: 'stage reached', inputType: 'ddl'},
       { columnName: 'lead committee', inputType: 'ddl', onlyText: true},
    ]
  });
}); 
