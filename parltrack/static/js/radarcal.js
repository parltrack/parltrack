jQuery(document).ready(function() {
    var eventclasses={
      // Prev DG PRES
      'Council: debate or examination expected' : 'council-debate-expected',
      'Council: final act scheduled' : 'council-final',
      'Council: political agreement on final act expected' : 'council-agree',
      'CSL 1R Agreement' : 'council-agree',
      'CSL Final Agreement' : 'council-agree',
      'Council: political agreement on position expected' : 'council-pos',
      'EP plenary sitting (indicative date)' : 'ep-sitting',
      'Indicative plenary sitting date, 1st reading/single reading' : 'ep-sitting',
      'EP 1R Plenary' : 'ep-sitting',
      'EP plenary sitting, 2nd reading (indicative date)' : 'ep-2ndsitting',
      'EP 2R Plenary' : 'ep-2ndsitting',
      'Indicative plenary sitting date, 2nd reading' : 'ep-2ndsitting',
      'EP plenary sitting, 3rd reading (indicative date)' : 'ep-3rdsitting',
      'Indicative plenary sitting date, 3rd reading' : 'ep-3rdsitting',
      'EP 3R Plenary' : 'ep-3rdsitting',
      'Plenary sitting agenda, debate' : 'ep-debate',
      'Debate scheduled' : 'ep-debate',
      'EP: report scheduled for adoption in committee, 1st or single reading' : 'ep-1streading',
      'EP 1R Committee' : 'ep-1streading',
      'Vote scheduled in committee, 1st reading/single reading' : 'com-vote',
      'Prev Adopt in Cte' : 'ep-1streading',
      'EP: report scheduled for adoption in committee, 2nd reading': 'ep-2ndreading',
      'Vote scheduled' : 'ep-vote',
      'Deadline Amendments' : 'tabling-deadline',
      'Deadline for 2nd reading in plenary' : '2ndreading-deadline',
      'Plenary sitting agenda, vote' :  'ep-vote'
    };
    var events=[];
    jQuery('.vevent').each(function() {
       var type=jQuery(this).find('span.summary').text();
       var eventclass;
       if(/EP: on [A-Z]* agenda/.test(type)) {
          eventclass="committee-agenda";
       } else if(/(EP: [A-Z]* Deadline for tabling ammendments|.* Tabling Deadline)/.test(type)) {
          eventclass="tabling-deadline";
       } else {
          eventclass=eventclasses[type];
       }
       if(!eventclass){
          //console.log(type);
          eventclass="cal-other";
       }
       var item;
       if(jQuery(this).parent().prev().text()=="More..") {
          item={
             title : jQuery(this).parent().parent().prev().text(),
             summary : jQuery(this).parent().parent().next().next().next().text(),
             type  : type,
             url   : jQuery(this).parent().parent().prev().find("a").attr('href'),
             start : jQuery(this).find(".dtstart").text(),
             className: eventclass
          };
       } else {
          item={
             title : jQuery(this).parent().prev().text(),
             summary : jQuery(this).parent().next().next().next().text(),
             type  : type,
             url   : jQuery(this).parent().prev().find("a").attr('href'),
             start : jQuery(this).find(".dtstart").text(),
             className: eventclass
          };
       }
       events.push(item);
    });
    jQuery('#categories').hide();
    jQuery('#legend').show();
    jQuery('#calendar').fullCalendar({
        events : events,
        weekends: false,
        weekMode: 'liquid',
        contentHeight: 500,
        defaultView: "month",
        eventRender: function(event, element) {
          element.qtip({content: '<div class="'+event.className+'">'+event.type+"</div><div>"+event.summary+"</div>",
                        tip: 'bottomLeft',
                        style: {
                          padding: 2,
                          border: { width: 2 }},
                        position: {
                          corner: {
                            target: 'mouse',
                            tooltip: 'bottomLeft'
                          }
                        },
                        adjust: {y: 10,
                                 screen: true,
                                 mouse: false}
                      });}
    });
});

