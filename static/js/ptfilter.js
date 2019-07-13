function get_options(filtered, filter_groups) {
   var ordered = [];
   for(key in filtered) {
      ordered.push(key);
   }
   // also add filter group labels to list of filter values to be ordered.
   for(k in (filter_groups || [])) {
      ordered.push(k);
   }
   return ordered.sort();
}

function filter(table) {
   // add filter row after header row
   $('#'+table+' thead').append('<tr id="'+table+'_filterrow"></tr>');
   // reference to newly created filter row
   var frow = $('#'+table+'_filterrow');
   // find all columns which have data-filter set to 'ddl' those are our columns of interest
   // we need to populate var filtered with those
   var filtered={}; 
   var filter_groups={};
   $('#'+table+' th').each(function(idx,el) {
      if($(el).data('filter')=="ddl") {
         filtered[idx]={};
         if($(el).data('filter-group')) {
            filter_groups[idx]=$(el).data('filter-group');
         }
      }
      // append a td to the filter-row
      frow.append("<td></td>");
   });

   // initially populate filtered variable
   // iterate through all data rows and aggregate all unique values for columns which are of interest
   $('#'+table+' tbody tr').each(function(idx, tr) {
      // check each column in this row
      $(tr).find('td').each(function(tidx,td) {
         if(filtered[tidx] == undefined) return; // skip this column, it is not of our interest
         val=$(td).text().trim(); // get the value of this column
         if(val == '') return;    // we ignore empty values
         // append current row to filtered[columnindex][value] which is a list
         if(filtered[tidx][val] == undefined) filtered[tidx][val]=[tr];
         else filtered[tidx][val].push(tr)
      })
   });

   // create dropdown in the filter row of the header
   frow.find('td').each(function(idx, td) { // iterate over all columns
      if(filtered[idx] == undefined) return; // skip: this column is not of interest
      // create widget for the filter in this column
      $(td).append('<div id="'+table+'_'+idx+'" class="ui fluid multiple search selection dropdown"><input type="hidden"><i class="dropdown icon"></i><div class="default text">Filter</div><div class="menu">');
      // get reference to this filter dropdown.
      var options=$(td).find('div[class=menu]');
      // prepare to order values in this filter including relevant filter groups
      var ordered = get_options(filtered[idx], filter_groups[idx]);
      // order filter values and add them to the options of the dropdown list
      for(key in ordered) {
         key = ordered[key];
         var x = options.append('<div class="item">'+key+'</div>').children().last();
         $(x).attr('data-value', key);
      }
   });

   // activate semantic-ui dropdown on filter widget.
   $('#'+table+' .ui.dropdown').dropdown({
      delimiter: 'xxxxxYYxxxx',
      onChange: function(value, text, selectedItem) {
         // make a "list" of all data rows
         var show = {};
         $('#'+table+' tbody tr').each(function(idx, el) {
            show[idx] = el;
         });
         var refiltered = {};
         var prefilled_refilters = {};
         // iterate over all filter widgets which have something set to filter
         $('#'+table+' thead input[value]').each(function(idx, input) {
            var selected = $(input).attr('value'); // filter expression
            if(selected  == "") return; // we ignore empty strings
            var col = $(input).parent().attr('id').split('_')[1]; // get column index
            selected = selected.split('xxxxxYYxxxx'); // split filter expression into values
            var values = [];
            refiltered[col]={};
            prefilled_refilters[col] = true;
            for(key in filtered[col]) {
               if($.inArray(key, selected)!=-1) continue;
               refiltered[col][key] = {};
            }

            if(filter_groups[col]) {
               // expand filter_group labels into the filter expression
               for(sval in selected) { // iterate over filter expression
                  var fg = filter_groups[col][selected[sval]] || [];
                  if(fg.length > 0) { // current expression is a filter-group label, expand it
                     for(fgi in fg) {
                        values.push(fg[fgi]);
                     }
                  } else { // no the current expression is a simple value
                     values.push(selected[sval]);
                  }
               }
            } else {
               // no filter groups defined for this column
               values = selected;
            }
            // iterate over all data rows and filter out those not matched by the filter expression
            for(rowkey in show) {
               var row = show[rowkey];
               var found = false;
               for(key in values){ // iterate over all values in filter expression
                  for(trkey in filtered[col][values[key]]) { // iterate over all rows matching current filter expression value
                     tr = filtered[col][values[key]][trkey]; // recover row
                     if(row == tr) {
                        found = true; // this row is covered by the current filter expression
                        break;
                     }
                  }
                  if(found) break;
               }
               if(!found) { // current row in show is not covered by filter expression, mark it for hiding
                  delete show[rowkey];
               }
            }
         });
         // show all rows that remain in show, hide all others
         $('#'+table+' tbody tr').each(function(idx, el) {
            if(show[idx] == undefined)  {
               $(el).hide();
            } else {
               $(el).show();
            }
         });
         // rebuild filter widget options
         // iterate over all shown rows
         for(row in show) {
            // check each column
            $(show[row]).find('td').each(function(tidx,td) {
               if(prefilled_refilters[tidx] == true) return;
               if(filtered[tidx] == undefined) return; // skip this column, it is not of our interest
               val=$(td).text().trim(); // get the value of this column
               if(val == '') return;    // we ignore empty values
               if(refiltered[tidx] == undefined) refiltered[tidx]={};
               if(refiltered[tidx][val] == undefined) refiltered[tidx][val]={};
            });
         }
         for(col in refiltered) {
            var ordered = [];
            for(key in refiltered[col]) {
               ordered.push(key);
            }

            // if there is more than 1 filter-group that has values in ordered add all filter-groups that have non-zero matches.
            var group_values = {};
            for(groupname in filter_groups[col]) {
               for(key in filter_groups[col][groupname]) {
                  if($.inArray(filter_groups[col][groupname][key], ordered)!=-1) {
                     group_values[groupname]={};
                  }
               }
            }
            for(key in group_values) {
               ordered.push(key);
            }
            
            ordered = ordered.sort();
            var values = []; //[ {value, text, name} ]
            for(key in ordered) {
               values.push({'value': ordered[key], 'text': ordered[key], 'name': ordered[key]});
            }

            $('#'+table+'_'+col).dropdown('setup menu', { 'values': values });
         }
      },
      clearable: true
   });

   // handle default filters
   $('#'+table+' th').each(function(idx,el) {
      if(!$(el).attr('data-default-filter')) return;
      $('#'+table+'_'+idx).dropdown('set selected', $.parseJSON($(el).attr('data-default-filter')));
   });
}
