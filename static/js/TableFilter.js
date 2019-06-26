window.picnet = window.picnet || {};
window.picnet.ui = window.picnet.ui || {};
window.picnet.ui.filter = window.picnet.ui.filter || {};

(function ($) {
    $.fn.tableFilter = function(method) {
        // plugin's default options
        var defaults = {
            thead:               null,
            columnFilters:       [],
            additionalFilters:   [],
            clearFilterControls: [],
            filterDelay:         200,
            enableCookies:       true,
            filteringRows:       function() {},
            filteredRows:        function() {},
            shouldFilterRow:     null,
            useAsyncInit:        false
        };
        var settings = {};

        var methods = {
            init: function (options) {
                settings = $.extend({}, defaults, options);
                // iterate through all the DOM elements we are attaching the plugin to
                return this.each(function () {
                    var $self = $(this); // reference the jQuery version of the current DOM element
                    methods.setup.apply(this, Array.prototype.slice.call(arguments, 1));
                });
            },
            // setup each table
            setup: function() {
                var jqSelf = $(this);
                var tableFilterObj = jqSelf.data('tableFilter');
                //if (tableFilterObj === undefined || tableFilterObj === null) {
                    var tableFilterObj = new picnet.ui.filter.TableFilter(this, settings);
                    jqSelf.data('tableFilter', tableFilterObj);  
                //}
                return this;
            },

            applyFilter: function () {
                // iterate through all the DOM elements we are attaching the plugin to
                return this.each(function () {
                    var tableFilterObj = $(this).data('tableFilter');
                    if (tableFilterObj === undefined || tableFilterObj === null) {
                        $.error('TableFilter not initialized!');
                    } else {
                        tableFilterObj.applyFilter();
                    }
                });
            },

            clearAllFilters: function () {
                // iterate through all the DOM elements we are attaching the plugin to
                return this.each(function () {
                    var tableFilterObj = $(this).data('tableFilter');
                    if (tableFilterObj === undefined || tableFilterObj === null) {
                        $.error('TableFilter not initialized!');
                    } else {
                        tableFilterObj.clearAllFilters();
                    }
                });
            },

            reload: function () {
                // iterate through all the DOM elements we are attaching the plugin to
                return this.each(function () {
                    var tableFilterObj = $(this).data('tableFilter');
                    if (tableFilterObj === undefined || tableFilterObj === null) {
                        $.error('TableFilter not initialized!');
                    } else {
                        tableFilterObj.reload();
                    }
                });
            }
        };

        // if a method as the given argument exists (arguments variable is always available in a function)
        if (methods[method]) {
           return methods[method].apply(this, Array.prototype.slice.call(arguments, 1));
        } else if (typeof method === 'object' || !method) {
            // call the initialization method
            return methods.init.apply(this, arguments);
        } else {
            // trigger an error
            $.error('Method "' +  method + '" does not exist in tableFilter plugin!');
        }
    };
})(jQuery);



//////////////
picnet.ui.filter.TableFilterRow = function(tr, columnNames, onlyTexts, includeDatas) {
    this._isMatch = true;

    var cells = tr.cells;
    var allRowText = '';
    var cellsLength = cells.length;
    for (var cellIndex = 0; cellIndex < cellsLength; cellIndex++) {
        var columnName = columnNames[cellIndex];
        var includeData = includeDatas[cellIndex];
        if (columnName && includeData) {
            var cellHtml = cells[cellIndex].innerHTML;
            this[columnName] = cellHtml;
            if (onlyTexts[cellIndex]) {
                var text = (cells[cellIndex].innerText || picnet.trim(cells[cellIndex].textContent));
                this[columnName + '_text'] = text;
                allRowText += text;
                allRowText += '\t';
            } else {
                allRowText += cellHtml;
                allRowText += '\t';    
            }
        }
    }
    this._allText = allRowText;
    this._tr = tr;
};

picnet.trim = function trim(str) {
    str = str.replace(/^\s+/, '');
    for (var i = str.length - 1; i >= 0; i--) {
        if (/\S/.test(str.charAt(i))) {
            str = str.substring(0, i + 1);
            break;
        }
    }
    return str;
};

///////////////

picnet.ui.filter.TableFilterOptions = function () {};
picnet.ui.filter.TableFilterOptions.prototype.columnFilters = [];
picnet.ui.filter.TableFilterOptions.prototype.additionalFilters = [];
picnet.ui.filter.TableFilterOptions.prototype.clearFilterControls = [];
picnet.ui.filter.TableFilterOptions.prototype.filterDelay = 200;
picnet.ui.filter.TableFilterOptions.prototype.enableCookies = true;
picnet.ui.filter.TableFilterOptions.prototype.filteringRows = function() {};
picnet.ui.filter.TableFilterOptions.prototype.filteredRows = function() {};

///////////////


picnet.ui.filter.FilterState = function(id, value, columnIndex, type) {
    this.id = id;
    this.value = value;
    this.columnIndex = columnIndex;
    this.type = type;    
};

picnet.ui.filter.FilterState.prototype.toString = function() { return this.id + ',' + this.value + ',' + this.columnIndex + ',' + this.type; };

picnet.ui.filter.FilterState.getFilterStatesFromCookie = function(cookieId) {                                    
    var filterState = $.cookie(cookieId);
    if (!filterState) { return null; }
    filterState = filterState.split('|');
    var states = [];
    for (var i = 0; i < filterState.length; i++) {
        var state = filterState[i].split(',');
        states.push(new picnet.ui.filter.FilterState(state[0], state[1], parseInt(state[2], 10), state[3]));
    }            
    return states;
};

picnet.ui.filter.FilterState.saveFilterStatesToCookie = function (filterStates, cookieId) {
    var cookieString = '';
    var length = filterStates.length;
    for (var i = 0; i < length; i++) {
        if (cookieString.length > 0) {
            cookieString += '|';
        };
        cookieString += filterStates[i].toString();
    }
    $.cookie(cookieId, cookieString, { expires: 999999 });
};

///////////////


picnet.ui.filter.SearchEngine = function() {};

picnet.ui.filter.SearchEngine.prototype.doesTextMatchTokens = function (textToMatch, postFixTokens, exactMatch) {
    if (!postFixTokens) return true;
    textToMatch = exactMatch ? textToMatch : textToMatch.toLowerCase();
    
    var stackResult = [];
    var stackResult1;
    var stackResult2;

    for (var i = 0; i < postFixTokens.length; i++) {
        var token = postFixTokens[i];
        token = exactMatch ? token : token.toLowerCase();
        if (token !== 'and' && token !== 'or' && token !== 'not') {
            if (token.indexOf('>') === 0 || token.indexOf('<') === 0 || token.indexOf('=') === 0 || token.indexOf('!=') === 0) {
                stackResult.push(this.doesNumberMatchToken(token, textToMatch));
            } else {
                stackResult.push(exactMatch ? textToMatch === token : textToMatch.indexOf(token) >= 0);
            }
        }
        else {

            if (token === 'and') {
                stackResult1 = stackResult.pop();
                stackResult2 = stackResult.pop();
                stackResult.push(stackResult1 && stackResult2);
            }
            else if (token === 'or') {
                stackResult1 = stackResult.pop();
                stackResult2 = stackResult.pop();

                stackResult.push(stackResult1 || stackResult2);
            }
            else if (token === 'not') {
                stackResult1 = stackResult.pop();
                stackResult.push(!stackResult1);
            }                
        }
    }
    return stackResult.length === 1 && stackResult.pop();
};

picnet.ui.filter.SearchEngine.prototype.parseSearchTokens = function(text) {
    if (!text) { return null; }
    text = text.toLowerCase();
    var normalisedTokens = this.normaliseExpression(text);
    normalisedTokens = this.allowFriendlySearchTerms(normalisedTokens);
    var asPostFix = this.convertExpressionToPostFix(normalisedTokens);
    var postFixTokens = asPostFix.split('|');
    return postFixTokens;
};
    
picnet.ui.filter.SearchEngine.prototype.doesNumberMatchToken = function(token, text) {
    var op,exp,actual = this.getNumberFrom(text);    
    if (token.indexOf('=') === 0) {
        op = '=';
        exp = parseInt(token.substring(1), 10);
    } else if (token.indexOf('!=') === 0) {
        op = '!=';
        exp = parseInt(token.substring(2), 10);
    } else if (token.indexOf('>=') === 0) {
        op = '>=';
        exp = parseInt(token.substring(2), 10);
    } else if (token.indexOf('>') === 0) {
        op = '>';
        exp = parseInt(token.substring(1), 10);
    } else if (token.indexOf('<=') === 0) {
        op = '<=';
        exp = parseInt(token.substring(2), 10);
    } else if (token.indexOf('<') === 0) {
        op = '<';
        exp = parseInt(token.substring(1), 10);
    } else {
        return true;
    }

    switch (op) {
        case '!=': return actual !== exp;
        case '=': return actual === exp;
        case '>=': return actual >= exp;
        case '>': return actual > exp;
        case '<=': return actual <= exp;
        case '<': return actual < exp;
    }
    throw new Error('Could not find a number operation: ' + op);
};

picnet.ui.filter.SearchEngine.prototype.getNumberFrom = function(txt) {
    if (txt.charAt(0) === '$') {
        txt = txt.substring(1);
    }
    return parseInt(txt, 10);
};
        
picnet.ui.filter.SearchEngine.prototype.normaliseExpression = function(text) {
    var textTokens = this.getTokensFromExpression(text);
    var normalisedTokens = [];

    for (var i = 0; i < textTokens.length; i++) {
        var token = textTokens[i];
        token = this.normaliseTerm(normalisedTokens, token, '(');
        token = this.normaliseTerm(normalisedTokens, token, ')');

        if (token.length > 0) { normalisedTokens.push(token); }
    }
    return normalisedTokens;
};

picnet.ui.filter.SearchEngine.prototype.normaliseTerm = function(tokens, token, term) {
    var idx = token.indexOf(term);
    while (idx !== -1) {
        if (idx > 0) { tokens.push(token.substring(0, idx)); }

        tokens.push(term);
        token = token.substring(idx + 1);
        idx = token.indexOf(term);
    }
    return token;
};

picnet.ui.filter.SearchEngine.prototype.getTokensFromExpression = function(exp) {        
    exp = exp.replace('>= ', '>=').replace('> ', '>').replace('<= ', '<=').replace('< ', '<').replace('!= ', '!=').replace('= ', '=');
    var regex = /([^"^\s]+)\s*|"([^"]+)"\s*/g;        
    var matches = [];
    var match = null;
    while (match = regex.exec(exp)) { matches.push(match[1] || match[2]); }
    return matches;
};

picnet.ui.filter.SearchEngine.prototype.allowFriendlySearchTerms = function(tokens) {
    var newTokens = [];
    var lastToken;

    for (var i = 0; i < tokens.length; i++) {
        var token = tokens[i];
        if (!token || token.length === 0) { continue; }
        if (token.indexOf('-') === 0) {
            token = 'not';
            tokens[i] = tokens[i].substring(1);
            i--;
        }
        if (!lastToken) {
            newTokens.push(token);
        } else {
            if (lastToken !== '(' && lastToken !== 'not' && lastToken !== 'and' && lastToken !== 'or' && token !== 'and' && token !== 'or' && token !== ')') {
                newTokens.push('and');
            }
            newTokens.push(token);
        }
        lastToken = token;
    }
    return newTokens;
};

picnet.ui.filter.SearchEngine.prototype.convertExpressionToPostFix = function(normalisedTokens) {
    var postFix = '';
    var stackOps = [];
    var stackOperator;
    for (var i = 0; i < normalisedTokens.length; i++) {
        var token = normalisedTokens[i];
        if (token.length === 0) continue;
        if (token !== 'and' && token !== 'or' && token !== 'not' && token !== '(' && token !== ')') {
            postFix = postFix + '|' + token;
        }
        else {
            if (stackOps.length === 0 || token === '(') {
                stackOps.push(token);
            }
            else {
                if (token === ')') {
                    stackOperator = stackOps.pop();
                    while (stackOperator !== '(') {
                        postFix = postFix + '|' + stackOperator;
                        stackOperator = stackOps.pop();
                    }
                }
                else if (stackOps[stackOps.length - 1] === '(') {
                    stackOps.push(token);
                } else {
                    while (stackOps.length !== 0) {
                        if (stackOps[stackOps.length - 1] === '(') { break; }
                        if (picnet.ui.filter.SearchEngine.EPrecedence[stackOps[stackOps.length - 1]] > picnet.ui.filter.SearchEngine.EPrecedence[token]) {
                            stackOperator = stackOps.pop();
                            postFix = postFix + '|' + stackOperator;
                        }
                        else { break; }
                    }
                    stackOps.push(token);
                }
            }
        }
    }
    while (stackOps.length > 0) { postFix = postFix + '|' + stackOps.pop(); }
    return postFix.substring(1);
};

picnet.ui.filter.SearchEngine.EPrecedence = {
    or: 1,
    and: 2,
    not: 3
};


//////////////////////
/* INIT START */
picnet.ui.filter.TableFilter = function(table, options) {    
    // DOM Objects
    if (options.thead && options.thead.jquery) {
        this.thead = options.thead[0];
    } else {
        this.thead = table.getElementsByTagName('thead')[0];
    }

    this.tbody = table.getElementsByTagName('tbody')[0];
    
    this.tableFilterRows = []; //  !TableFilterRow[]
    this.tableFilterRowLength = 0;
    this.tableFilterNumberOfTotalRowsInTableIncludingHidden = 0;
    
    // column arrays, use column index to index
    this.columnNames = []; // !string[], sparse
    this.includeDatas = []; // !string[], sparse
    this.columnFilters = []; // [],sparse
    this.columnFilterCtrls = []; // jquery dom[] , sparse
    this.columnFilterInputTypes = []; // !string[], sparse
    this.columnOnlyTexts = []; // bool[], sparse
    this.columnFilterLength = 0;
      
    // additional filter arrays
    this.additionalFilterCtrls = [];
    this.additionalFilterInputTypes = [];
    this.additionalFilters = options.additionalFilters;
    this.additionalFilterLength = this.additionalFilters.length;
    
    // clear filter controls
    this.clearFilterControls = options.clearFilterControls;
    this.clearFilterControlLength = this.clearFilterControls.length;
    
    // global variables
    this.enableCookies = options.enableCookies;
    this.filterDelay = options.filterDelay;
    this.filteringRows = options.filteringRows;
    this.filteredRows = options.filteredRows;
    this.shouldFilterRow = options.shouldFilterRow;
    this.lastkeytime;  // number
    this.lastTimer;  // number  
    this.cancelQuickFind; // boolean
    var listid = table.getAttribute('id') || table.getAttribute('name') || '';
    this.cookieId = listid + '_' + (++picnet.ui.filter.TableFilter.filteridx) + '_filters';
    this.search = new picnet.ui.filter.SearchEngine();

    // Initalise columnNames, columnFilters, columnFilterLength
    this.initialiseColumnNamesAndColumnFilters(options.columnFilters);
    // Initialise tableFilterRows, tableFilterRowLength, tableFilterNumberOfTotalRowsInTableIncludingHidden
    if (options.useAsyncInit) {
        this.createTableFilterRowsAsync(0, 0, function() {
        this.continueInitialization(options);
      });
    } else {
        this.createTableFilterRows();
        this.continueInitialization(options);
    }
};

picnet.ui.filter.TableFilter.filteridx = 0;

picnet.ui.filter.TableFilter.prototype.continueInitialization = function(options) {    
    // Initialise columnFilterCtrls, columnFilterInputTypes//
    this.buildFiltersRow();
    // check if controls are JQuery object, if not create it
    this.ensureCtrlsAreJQuery(options.clearFilterControls, null);
    this.ensureCtrlsAreJQuery(options.additionalFilters, 'control');
    // Initialises additionalFilterCtrls, additionalFilterInputTypes
    // registers listeners to the controls   
    this.registerListenersOnControls();          

    var filterStates = picnet.ui.filter.FilterState.getFilterStatesFromCookie();
    if (filterStates) {
        this.setFilterValueFromFilterState(filterStates);
        this.doFiltering(filterStates);
    }
};

picnet.ui.filter.TableFilter.prototype.initialiseColumnNamesAndColumnFilters = function(denseColumnFilters) {    
    var columnFilterLength = denseColumnFilters.length;
    this.columnFilterLength = columnFilterLength; 
    for (var colIdx = 0; colIdx < columnFilterLength; colIdx++) {
        var columnFilter = denseColumnFilters[colIdx];
        this.includeDatas[colIdx] = (columnFilter.includeData !== false);
        this.columnNames[colIdx] = columnFilter.columnName;
        this.columnFilters[colIdx] = columnFilter;
        this.columnOnlyTexts[colIdx] = columnFilter.onlyText;
    }
};

picnet.ui.filter.TableFilter.prototype.createTableFilterRows = function() {                        
    var columnNames = this.columnNames;
    var tableRows = this.tbody.rows;
    var columnOnlyTexts = this.columnOnlyTexts;
    var includeDatas = this.includeDatas;
    var tableRowsLength = tableRows.length;
    this.tableFilterNumberOfTotalRowsInTableIncludingHidden = tableRowsLength;
    
 
    if (!this.shouldFilterRow) {
        this.tableFilterRowLength = tableRowsLength;
        for(var i =0; i < tableRowsLength; i++) {
            this.tableFilterRows[i] = new picnet.ui.filter.TableFilterRow(tableRows[i], columnNames, columnOnlyTexts, includeDatas);
        }
    } else {
        var shouldFilterRowFunction = this.shouldFilterRow;
        var visibleRowIndex = 0;

	for(var i =0; i < tableRowsLength; i++) {
            if (!shouldFilterRowFunction(i, tableRows[i])) {
                this.tableFilterRows[visibleRowIndex] = new picnet.ui.filter.TableFilterRow(tableRows[i], columnNames, columnOnlyTexts, includeDatas);
                visibleRowIndex++;
            }
        }
        this.tableFilterRowLength = visibleRowIndex;
    }    
};

picnet.ui.filter.TableFilter.prototype.createTableFilterRowsAsync = function (startRow, visibleRowIndex, funcContinueInit) {
    var columnNames = this.columnNames;
    var tableRows = this.tbody.rows;
    var columnOnlyTexts = this.columnOnlyTexts;
    var includeDatas = this.includeDatas;
    var tableRowsLength = tableRows.length;
    this.tableFilterRowLength = tableRowsLength;
      
    var startTicks = new Date().getTime();
   
    if (this.shouldFilterRow) {
        for (var i = startRow; i < tableRowsLength; i++) {
            this.tableFilterRows[i] = new picnet.ui.filter.TableFilterRow(tableRows[i], columnNames, columnOnlyTexts, includeDatas);
            if (i - startRow > 100 && new Date().getTime() - startTicks > 200) {
                var thisObj = this;
                var nextRowNo = i+1;
                setTimeout(function () {
                    picnet.ui.filter.TableFilter.prototype.createTableFilterRowsAsync.call(thisObj, nextRowNo, nextRowNo, funcContinueInit); 
                }, 5);
                return;
            }
        }
    } else {
        var shouldFilterRowFunction = this.shouldFilterRow;
        var visibleRowIndex = 0;

	for(var i = startRow; i < tableRowsLength; i++) {
            if (shouldFilterRowFunction(i, tableRows[i])) {
                this.tableFilterRows[visibleRowIndex] = new picnet.ui.filter.TableFilterRow(tableRows[i], columnNames, columnOnlyTexts, includeDatas);
                visibleRowIndex++;
                if (i - startRow > 100 && new Date().getTime() - startTicks > 200) {
                    var thisObj = this;
                    var nextRowNo = i+1;
                    setTimeout(function () {
                        picnet.ui.filter.TableFilter.prototype.createTableFilterRowsAsync.call(thisObj, nextRowNo, visibleRowIndex, funcContinueInit); 
                    }, 5);
                    return;
                }
            }
        }

    }
    funcContinueInit.call(this);
};

    
picnet.ui.filter.TableFilter.prototype.buildFiltersRow = function() {
    var tr = document.createElement('tr');
    tr.className = 'filters';
      var length = this.columnFilterLength;
    for (var colIdx = 0; colIdx < length; colIdx++) {
        var columnFilter = this.columnFilters[colIdx];

        // Create filter cell and add filter control
        var td = document.createElement('td');

        if (columnFilter) {
            if (columnFilter.filterClass) { $(td).addClass(columnFilter.filterClass); }

            var jqFilterCtrl = null;
            if (columnFilter.inputType === 'custom' || columnFilter.control) {
                jqFilterCtrl = columnFilter.control.jquery ? columnFilter.control : $(columnFilter.control);
            }
            else if (columnFilter.inputType === 'text') {
                jqFilterCtrl = this.getTextFilterJQueryCtrl(colIdx);
            }
            else if (columnFilter.inputType === 'ddl') {
                if (this.columnOnlyTexts[colIdx]) {
                    jqFilterCtrl = $(this.getSelectFilterString(colIdx, this.columnNames[colIdx] + '_text'));
                } else {
                    jqFilterCtrl = $(this.getSelectFilterString(colIdx, this.columnNames[colIdx]));
                }
            }

            if (columnFilter.colSpan) {
                td.colSpan = columnFilter.colSpan;
            }
        
            if (jqFilterCtrl) {
                td.appendChild(jqFilterCtrl[0]);
                this.columnFilterCtrls[colIdx] = jqFilterCtrl;
                this.columnFilterInputTypes[colIdx] = columnFilter.inputType;
            }

            if (columnFilter.createHeaderFilterCell !== false) {
                tr.appendChild(td);
            }
        }
    }
    this.thead.appendChild(tr);       
};


picnet.ui.filter.TableFilter.prototype.getTextFilterJQueryCtrl = function(colIdx) {
    var toolTipMessage = this.columnFilters[colIdx].toolTipMessage;
    if (toolTipMessage) {
        toolTipMessage = toolTipMessage.replace('"','&#034;');
    } else toolTipMessage = '';
    var ctrl = $('<input type="text" id="filter_' + colIdx + '" class="filter" title="' + toolTipMessage + '" style="width: 95%;" />');
    return ctrl;
};

picnet.ui.filter.TableFilter.prototype.emptyDefaultText = function(jQueryCtrl, colIdx) {
    var defaultText = colIdx < 0 ? (this.additionalFilters[-(colIdx+1)].defaultText || '') : (this.columnFilters[colIdx].defaultText || '');
    if (jQueryCtrl.val() === defaultText) {
        jQueryCtrl.val('');
        var normalTextColor = colIdx < 0 ? (this.additionalFilters[-(colIdx+1)].normalTextColor || '#000') : (this.columnFilters[colIdx].normalTextColor || '#000');
        jQueryCtrl.css('color',  normalTextColor);
    }
    return true;
};

picnet.ui.filter.TableFilter.prototype.setDefaultText = function(jQueryCtrl, colIdx) {
    var defaultText = colIdx < 0 ? (this.additionalFilters[-(colIdx+1)].defaultText || '') : (this.columnFilters[colIdx].defaultText || '');
    jQueryCtrl.val(defaultText);
    var defaultTextColor = colIdx < 0 ? (this.additionalFilters[-(colIdx+1)].defaultTextColor || '#000') : (this.columnFilters[colIdx].defaultTextColor || '#000');
    jQueryCtrl.css('color',  defaultTextColor);
};

picnet.ui.filter.TableFilter.prototype.getSelectFilterString = function(colIdx, propertyName) {
    var select = '<select id=\"filter_' + colIdx;
    select += '\" class=\"filter\" style=\"width: 95%; \"><option value=\"\">';
    var selectOptionLabel = this.columnFilters[colIdx].selectOptionLabel;
    if (selectOptionLabel) {
        select += selectOptionLabel.replace('"','&#034;');
    }
    select += '</option>';      
    
    var tableFilterRows = this.tableFilterRows;
    var length = this.tableFilterRowLength;
      
    var temp = {}
    var valuesUnique = [];
    for (var i = 0; i < length; i++) {
        var val = tableFilterRows[i][propertyName];
         temp[val] = null;
    }
    for (var tval in temp) {
         valuesUnique.push(tval);
    }
    valuesUnique.sort();
        
    length = valuesUnique.length;
    for (var i = 0; i < length; i++) {
        var txt = valuesUnique[i];
        select += '<option value=\"' + txt.replace('"','&#034;') + '\">' + txt + '</option>';
    }
    select += '</select>';

    return select;
};


picnet.ui.filter.TableFilter.prototype.ensureCtrlsAreJQuery = function (controls, propertyName) {
    var length = controls.length;
    for (var i = 0; i < length; i++) {
        if (propertyName) {
            var ctrl = controls[i][propertyName];
            if (!ctrl.jquery) controls[i][propertyName] = $(ctrl);
        }
        else {
            var ctrl = controls[i];
            if (!ctrl.jquery) controls[i] = $(ctrl);
        }
    }
}

picnet.ui.filter.TableFilter.prototype.registerListenersOnControls = function () {
    var self = this;
    var columnFilterCtrls = this.columnFilterCtrls;
    var columnFilterInputTypes = this.columnFilterInputTypes;
    var length = this.columnFilterLength;
    
    for (var i = 0; i < length; i++) {
        var filterCtrl = columnFilterCtrls[i];
        if (filterCtrl === undefined) continue;
        var type = columnFilterInputTypes[i];
        switch (type) {
            case 'text':
                filterCtrl[0].setAttribute('title', this.columnFilters[i].toolTipMessage);
                 filterCtrl.keyup(function() {
                    self.onFilterChanged();
                });
                var self = this;
                with ({ i: i, filterCtrl: filterCtrl }) {
                      filterCtrl.focus(function(eventarg) { self.emptyDefaultText(filterCtrl, i); });
                }
                this.setDefaultText(filterCtrl, i);
                break;        
            case 'ddl':
                filterCtrl.change(function() {
                    self.onFilterChanged();
                });
                break;
            case 'custom':
                this.columnFilters[i].setupTrigger(function() {
                    self.onFilterChanged();
                });
                break;
        }
    }
  
      var clearFilterControls = this.clearFilterControls;
      
    if (clearFilterControls) {
        length = this.clearFilterControlLength;
        for (var i = 0; i < length; i++) {
            clearFilterControls[i].click(function() {
                self.clearAllFilters();
            });
        }
    }

    var additionalFilters = this.additionalFilters;
    if (additionalFilters) {
          length = this.additionalFilterLength;
        for (var i = 0; i < length; i++) {
            var additionalFilter = additionalFilters[i];
            var additionalFilterCtrl = additionalFilter.control;
            var type = additionalFilter.inputType;
            switch (type) {
                   case 'text':
                    additionalFilterCtrl[0].setAttribute('title', additionalFilter.toolTipMessage);
                    additionalFilterCtrl.keyup(function() {
                        self.onFilterChanged();
                    });
                    var self = this;
                    with ({ i: i, additionalFilterCtrl: additionalFilterCtrl }) {
                          additionalFilterCtrl.focus(function(eventarg) { self.emptyDefaultText(additionalFilterCtrl, -(i+1)); });
                    }
                    this.setDefaultText(additionalFilterCtrl, -(i+1));
                    break;
                case 'ddl':
                    additionalFilterCtrl.change(function() {
                        self.onFilterChanged();
                    });
                    break;
                 case 'custom':
                    additionalFilter.setupTrigger(function() {
                        self.onFilterChanged();
                    });
                    break;
            }
            
            this.additionalFilterCtrls[i] = additionalFilter.control;
            this.additionalFilterInputTypes[i] = type;
        }
    }
};


picnet.ui.filter.TableFilter.prototype.setFilterValueFromFilterState = function(filterStates) {
    var length = filterStates.length;
    for (var i = 0; i < length; i++) {
        var state = filterStates[i];
        if (state.type && state.id) {
            var filter = $('#' + state.id); 
                        
            switch (state.type) {
                case 'ddl':
                    var options = filter.options;
                    var length = options.length;
                    for (var i = 0 ; i < length ; i++) {
                        var o = options[i];
                        if (o.value === state.value) 
                            o.setAttribute('selected', 'selected');
                        else o.removeAttribute('selected');
                    }
                    break;
                case 'text':                            
                    filter.value = state.value;
                    break;
                case 'custom':
                    if (state.columnIndex >= 0)    {
                        this.columnFilters[state.columnIndex].setValue(state.value);
                    } else {
                        this.additionalColumnFilters[-(state.columnIndex+1)].setValue(state.value);
                    }
                    break;
            }
           }
    }
}    

/* INIT End */

// applyFilter

picnet.ui.filter.TableFilter.prototype.applyFilter = function() {
    if (this.lastTimer) { this.lastTimer.stopTime(); this.lastTimer = null; }
    this.cancelQuickFind = false;
    var filterStates = this.getFilterStates();            
    this.doFiltering(filterStates);            
    if (this.enableCookies) { picnet.ui.filter.FilterState.saveFilterStatesToCookie(filterStates, this.cookieId); }                
};

picnet.ui.filter.TableFilter.prototype.reload = function () {
    this.tableFilterRows = [];
    this.createTableFilterRows();
};

// Clear filters, called from event

picnet.ui.filter.TableFilter.prototype.clearAllFilters = function() {
    var length = this.columnFilterLength;
    for (var i = 0; i < length; i++) {
        var filterCtrl = this.columnFilterCtrls[i];
        if (filterCtrl) {
            var type = this.columnFilterInputTypes[i];
            var setValueFunc = this.columnFilters[i].setValue;
            var defaultText = this.columnFilters[i].defaultText || '';
            var defaultTextColor = this.columnFilters[i].defaultTextColor || '#aaa';
            this.clearFilterValue(filterCtrl, type, setValueFunc, defaultText, defaultTextColor);
        }
    }

       length = this.additionalFilterLength;
    for (i = 0; i < length; i++) {
        var filterCtrl = this.additionalFilterCtrls[i];
        var type = this.additionalFilterInputTypes[i];
        var setValueFunc = this.additionalFilters[i].setValue;
        var defaultText = this.additionalFilters[i].defaultText || '';
        var defaultTextColor = this.additionalFilters[i].defaultTextColor || '#aaa';
        this.clearFilterValue(filterCtrl, type, setValueFunc, defaultText, defaultTextColor);
    }          
    this.applyFilter();
};
    
picnet.ui.filter.TableFilter.prototype.clearFilterValue = function(filter, type, setValueFunc, defaultText, defaultTextColor) {        
    switch (type) {
        case 'ddl':
            filter[0].selectedIndex = 0;
            break;
        case 'text':
            filter.val(defaultText);
            filter.css('color', defaultTextColor);
            break;
        case 'custom':
            if (setValueFunc) setValueFunc(null);
            break;
    }
};

// Triggers when a filter changes    

picnet.ui.filter.TableFilter.prototype.onFilterChanged = function (e) {
    this.lastkeytime = new Date().getTime();
    this.quickFindTimer();
};

picnet.ui.filter.TableFilter.prototype.quickFindTimer = function() {
    if (this.lastTimer) { this.lastTimer.stopTime(); this.lastTimer = null; } 
    this.cancelQuickFind = true;

    var curtime = new Date().getTime();
    var delay = this.filterDelay;        
    if (curtime - this.lastkeytime >= delay) {
        this.cancelQuickFind = false;
        var filterStates = this.getFilterStates();            
        this.doFiltering(filterStates);        
        if (this.enableCookies) { picnet.ui.filter.FilterState.saveFilterStatesToCookie(filterStates, this.cookieId); }        
    } else {        
        this.lastTimer = $(this).oneTime(delay / 4, 'qf', function() { this.quickFindTimer.call(this); });
    }
};

// Do filter        

picnet.ui.filter.TableFilter.prototype.doFiltering = function(filterStates) {
    this.filteringRows(filterStates); // callback event                    
    this.resetRowsMatchState();
     
    for (var i = 0; i < filterStates.length; i++) {
        var state = filterStates[i];
        // if state is null or empty, continue to next filter
        if (!state.value || state.value.length == 0) {
            continue;
        }                
        this.doIndividualFilter(state);
    }

    var stats = this.showHideRows();
    this.filteredRows(filterStates, stats); // callback event                        
};

picnet.ui.filter.TableFilter.prototype.resetRowsMatchState = function () {
    var tableFilterRows = this.tableFilterRows;
    var length = this.tableFilterRowLength;
    for (var i = 0; i < length; i++) {
        tableFilterRows[i]._isMatch = true; 
    }
};

picnet.ui.filter.TableFilter.prototype.doIndividualFilter = function(filterState) {
    var normalisedTokens = this.getNormalisedSearchTokensForState(filterState);
    var filterValue = filterState.value;
    var exactMatch = filterState.type === 'ddl';
    var tableFilterRows = this.tableFilterRows;
    var length = this.tableFilterRowLength;
       
    if (filterState.type == 'custom') {
        var callback;
        var filterCtrl;
        if (filterState.columnIndex >= 0) {
            // column filter
            callback = this.columnFilters[filterState.columnIndex].matchFunction;
            filterCtrl = this.columnFilterCtrls[filterState.columnIndex];
        } else {
            // additional filter
               callback = this.additionalFilters[-(filterState.columnIndex+1)].matchFunction;
               filterCtrl = this.additionalFilterCtrls[-(filterState.columnIndex+1)];
        }
         for (var i = 0; i < length; i++) {
               if (this.cancelQuickFind) return;
            var tfr = tableFilterRows[i];    
            // already determined not to match so continue with next
            if (!tfr._isMatch) { continue; }
            if (!callback(filterCtrl, tfr, filterValue, normalisedTokens)) { tfr._isMatch = false; }
        }
    } else {
        var propertyName = null;
        if (filterState.columnIndex >= 0) {
            var onlyText = this.columnOnlyTexts[filterState.columnIndex]
            if (onlyText) {
                   propertyName = this.columnNames[filterState.columnIndex] + "_text";
               } else {
                   propertyName = this.columnNames[filterState.columnIndex];
               }
           }

         for (var i = 0; i < length; i++) {
            if (this.cancelQuickFind) return;
            var tfr = tableFilterRows[i];    
            // already determined not to match so continue with next
            if (!tfr._isMatch) { continue; }
            var textToMatch;
            if (propertyName) {
                // column filter
                textToMatch = tfr[propertyName];
            } else {
                // additional filter
                textToMatch = tfr._allText;
            }
            if (!this.search.doesTextMatchTokens(textToMatch, normalisedTokens, exactMatch)) { tfr._isMatch = false; }
        }
     }
};

picnet.ui.filter.TableFilter.prototype.getNormalisedSearchTokensForState = function(state) {
    if (state === null) { return null; }
    switch (state.type) {
        case 'ddl':
            return [state.value];
        case 'text':
            return this.search.parseSearchTokens(state.value);
        case 'custom':
            return [state.value];
    }
};

picnet.ui.filter.TableFilter.prototype.showHideRows = function() {
    var tableFilterRows = this.tableFilterRows;
    var length = this.tableFilterRowLength;
    var rowsVisible = 0;
    for (var i = 0; i < length; i++) {
        if (this.cancelQuickFind) return;
        var tfr = tableFilterRows[i];
        if (tfr._isMatch) {
            tfr._tr.style.display = 'table-row';
            rowsVisible++;
        } else {
            tfr._tr.style.display = 'none';
        }    
    }
    return { totalNumberOfRows: length, numberOfRowsVisible: rowsVisible};
};

// Get filter state from the filter controls

picnet.ui.filter.TableFilter.prototype.getFilterStates = function() {
    var filterStates = [];
    var length =  this.columnFilterLength;

    for (var i = 0; i < length; i++) {
        var filterCtrl = this.columnFilterCtrls[i];
        if (filterCtrl) {
            var columnFilter = this.columnFilters[i];
               var state = this.getFilterStateForFilter(filterCtrl, columnFilter, i);
            
            if (state) {
                state.columnIndex = i;
                filterStates.push(state); 
            }
        }
    }

    length = this.additionalFilterLength;
    var additionalFilterCtrls = this.additionalFilterCtrls;
    var additionalFilters = this.additionalFilters;
    
    for (i = 0; i < length; i++) {
        var filterCtrl = additionalFilterCtrls[i];
          
        if (filterCtrl) {
            var additionalFilter = additionalFilters[i];
            var columnIndex = -(i+1);
            var state = this.getFilterStateForFilter(filterCtrl, additionalFilter, columnIndex);
            
            if (state) {
                filterStates.push(state); 
            }
        }
    }
   
    return filterStates;
};


picnet.ui.filter.TableFilter.prototype.getFilterStateForFilter = function(filterCtrl, optFilter, columnIndex) {
    var type = optFilter.inputType || 'text';        
    var value;        
    switch (type) {
        case 'text':
            var defaultText;
            if (columnIndex >= 0) {
                defaultText = this.columnFilters[columnIndex].defaultText || '';
            } else {
                defaultText = this.additionalFilters[-(columnIndex+1)].defaultText || '';
            }
            value = filterCtrl.val();
            if (value === defaultText) value = null;
            if (value != null) value = value.toLowerCase();
            break;
        case 'ddl':
            value = filterCtrl[0].selectedIndex === 0 ? null : filterCtrl[0].options[filterCtrl[0].selectedIndex].value;
            break;
        case 'custom':
            value = optFilter.getValue();
            break
    }
    if (value == null || value.length <= 0) { return null; }            
    var state = new picnet.ui.filter.FilterState(filterCtrl.attr('id'), value, columnIndex, type);
        
    return state;
};




//



/**
 * jQuery.timers - Timer abstractions for jQuery
 * Written by Blair Mitchelmore (blair DOT mitchelmore AT gmail DOT com)
 * Licensed under the WTFPL (http://sam.zoy.org/wtfpl/).
 * Date: 2009/10/16
 *
 * @author Blair Mitchelmore
 * @version 1.2
 *
 **/

jQuery.fn.extend({
	everyTime: function(interval, label, fn, times) {
		return this.each(function() {
			jQuery.timer.add(this, interval, label, fn, times);
		});
	},
	oneTime: function(interval, label, fn) {
		return this.each(function() {
			jQuery.timer.add(this, interval, label, fn, 1);
		});
	},
	stopTime: function(label, fn) {
		return this.each(function() {
			jQuery.timer.remove(this, label, fn);
		});
	}
});

jQuery.extend({
	timer: {
		global: [],
		guid: 1,
		dataKey: "jQuery.timer",
		regex: /^([0-9]+(?:\.[0-9]*)?)\s*(.*s)?$/,
		powers: {
			// Yeah this is major overkill...
			'ms': 1,
			'cs': 10,
			'ds': 100,
			's': 1000,
			'das': 10000,
			'hs': 100000,
			'ks': 1000000
		},
		timeParse: function(value) {
			if (value == undefined || value == null)
				return null;
			var result = this.regex.exec(jQuery.trim(value.toString()));
			if (result[2]) {
				var num = parseFloat(result[1]);
				var mult = this.powers[result[2]] || 1;
				return num * mult;
			} else {
				return value;
			}
		},
		add: function(element, interval, label, fn, times) {
			var counter = 0;
			
			if (jQuery.isFunction(label)) {
				if (!times) 
					times = fn;
				fn = label;
				label = interval;
			}
			
			interval = jQuery.timer.timeParse(interval);

			if (typeof interval != 'number' || isNaN(interval) || interval < 0)
				return;

			if (typeof times != 'number' || isNaN(times) || times < 0) 
				times = 0;
			
			times = times || 0;
			
			var timers = jQuery.data(element, this.dataKey) || jQuery.data(element, this.dataKey, {});
			
			if (!timers[label])
				timers[label] = {};
			
			fn.timerID = fn.timerID || this.guid++;
			
			var handler = function() {
				if ((++counter > times && times !== 0) || fn.call(element, counter) === false)
					jQuery.timer.remove(element, label, fn);
			};
			
			handler.timerID = fn.timerID;
			
			if (!timers[label][fn.timerID])
				timers[label][fn.timerID] = window.setInterval(handler,interval);
			
			this.global.push( element );
			
		},
		remove: function(element, label, fn) {
			var timers = jQuery.data(element, this.dataKey), ret;
			
			if ( timers ) {
				
				if (!label) {
					for ( label in timers )
						this.remove(element, label, fn);
				} else if ( timers[label] ) {
					if ( fn ) {
						if ( fn.timerID ) {
							window.clearInterval(timers[label][fn.timerID]);
							delete timers[label][fn.timerID];
						}
					} else {
						for ( var fn in timers[label] ) {
							window.clearInterval(timers[label][fn]);
							delete timers[label][fn];
						}
					}
					
					for ( ret in timers[label] ) break;
					if ( !ret ) {
						ret = null;
						delete timers[label];
					}
				}
				
				for ( ret in timers ) break;
				if ( !ret ) 
					jQuery.removeData(element, this.dataKey);
			}
		}
	}
});

jQuery(window).bind("unload", function() {
	jQuery.each(jQuery.timer.global, function(index, item) {
		jQuery.timer.remove(item);
	});
});


/**
 * jQuery Cookie plugin
 *
 * Copyright (c) 2010 Klaus Hartl (stilbuero.de)
 * Dual licensed under the MIT and GPL licenses:
 * http://www.opensource.org/licenses/mit-license.php
 * http://www.gnu.org/licenses/gpl.html
 *
 */
 
jQuery.cookie = function (key, value, options) {

    // key and at least value given, set cookie...
    if (arguments.length > 1 && String(value) !== "[object Object]") {
        options = jQuery.extend({}, options);

        if (value === null || value === undefined) {
            options.expires = -1;
        }

        if (typeof options.expires === 'number') {
            var days = options.expires, t = options.expires = new Date();
            t.setDate(t.getDate() + days);
        }

        value = String(value);

        return (document.cookie = [
            encodeURIComponent(key), '=',
            options.raw ? value : encodeURIComponent(value),
            options.expires ? '; expires=' + options.expires.toUTCString() : '', // use expires attribute, max-age is not supported by IE
            options.path ? '; path=' + options.path : '',
            options.domain ? '; domain=' + options.domain : '',
            options.secure ? '; secure' : ''
        ].join(''));
    }

    // key and possibly options given, get cookie...
    options = value || {};
    var result, decode = options.raw ? function (s) { return s; } : decodeURIComponent;
    return (result = new RegExp('(?:^|; )' + encodeURIComponent(key) + '=([^;]*)').exec(document.cookie)) ? decode(result[1]) : null;
};
