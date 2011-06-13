$(document).ready(function() {
    var eventclasses={
      'Council: debate or examination expected' : 'council-debate-expected',
      'Council: final act scheduled' : 'council-final',
      'Council: political agreement on final act expected' : 'council-agree',
      'EP plenary sitting (indicative date)' : 'ep-sitting',
      'Plenary sitting agenda, debate' : 'ep-debate',
      'EP: report scheduled for adoption in committee, 1st or single reading' : 'ep-1streading',
      'Plenary sitting agenda, vote' :  'ep-vote'
    };
    var events=[];
    $('.vevent').each(function() {
       var eventclass=$(this).find('span.summary').text();
       events.push( {
          title : $(this).parent().prev().text(),
          type  : eventclass,
          url   : $(this).parent().prev().find("a").attr('href'),
          start : $(this).find(".dtstart").text(),
          className: eventclasses[eventclass]
       });
    });
    $('#categories').hide();
    $('#legend').show();
    $('#calendar').fullCalendar({
        events : events,
        weekends: false,
        weekMode: 'liquid',
        contentHeight: 500,
        defaultView: "month"
    });
});

