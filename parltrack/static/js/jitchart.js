var labelType, useGradients, nativeTextSupport, animate;

(function() {
  var ua = navigator.userAgent,
      iStuff = ua.match(/iPhone/i) || ua.match(/iPad/i),
      typeOfCanvas = typeof HTMLCanvasElement,
      nativeCanvasSupport = (typeOfCanvas == 'object' || typeOfCanvas == 'function'),
      textSupport = nativeCanvasSupport
        && (typeof document.createElement('canvas').getContext('2d').fillText == 'function');
  //I'm setting this based on the fact that ExCanvas provides text support for IE
  //and that as of today iPhone/iPad current text support is lame
  labelType = (!nativeCanvasSupport || (textSupport && !iStuff))? 'Native' : 'HTML';
  nativeTextSupport = labelType == 'Native';
  useGradients = nativeCanvasSupport;
  animate = !(iStuff || !nativeCanvasSupport);
})();

var getId = (function () {
  var incrementingId = 0;
  return function(element) {
    if (!element.id) {
      element.id = "id_" + incrementingId++;
      // Possibly add a check if this ID really is unique
    }
    return element.id;
  };
}());

var colormap={
   'PSE': '#EE1C23',
   'S&D': '#EE1C23',
   'Verts/ALE': '#009900',
   'ECR': '#0054A5',
   'PPE': '#6699FF',
   'PPE-DE': '#3099DB',
   'GUE/NGL': '#990000',
   'ALDE': '#FFD700',
   'NI': '#fff',
   'NA': '#fff',
   'ITS': '#000',
   'IND/DEM': '#F7AF20',
   'UEN': '#5d4fa5',
   'EFD': '#2ca8be',
}
$(document).ready(function() {
  //init data
  $('.votes-graph').each(function() {
      var labels=[];
      var colors=[];
      var vals=[]
      var values=[];
      var sum=0;
      count=0;
      $(this).next().find('td.for').each(function() {
         labels.push($(this).attr('title'));
         var c=colormap[$(this).attr('title')]
         //if (!c) {console.log($(this)); console.log($(this).attr('title'));}
         colors.push(c);
         count=(parseInt($(this).text()));
         values.push(count);
         sum+=count
      });
      vals.push( {
         label : "+"+sum,
         name : "+",
         values : values,
      });
      values=[];
      sum=0;
      $(this).next().find('td.against').each(function() {
         count=(parseInt($(this).text()));
         values.push(count);
         sum+=count
      });
      vals.push( {
         label : "-"+sum,
         name : "-",
         values : values,
      });
      values=[];
      sum=0;
      $(this).next().find('td.abstain').each(function() {
         count=(parseInt($(this).text()));
         values.push(count);
         sum+=count
      });
      vals.push( {
         label : "("+sum+")",
         name : "0",
         values : values,
      });
      var json = {
         label: labels,
         color: colors,
         values: vals
      };
      //init BarChart
      var id=getId(this);
      var barChart = new $jit.BarChart({
         //id of the visualization container
         injectInto: id,
         //whether to add animations
         animate: true,
         //horizontal or vertical barcharts
         orientation: 'horizontal',
         //bars separation
         barsOffset: 5,
         //visualization offset
         Margin: {
             top: 5,
             left: 5,
             right: 5,
             bottom: 5
         },
         //labels offset position
         //labelOffset: 15,
         //bars style
         type: useGradients? 'stacked:gradient' : 'stacked',
         //whether to show the aggregation of the values
         showAggregates: false,
         //whether to show the labels for the bars
         showLabels: true,
         //labels style
         Label: {
            type: labelType, //Native or HTML
            size: 13,
            family: 'Arial',
            style: 'bold',
            color: 'black'
         },
         //add tooltips
         Tips: {
                  enable: true,
                  onShow: function(tip, elem) {
                     tip.innerHTML = "<b>" + elem.name + "</b>: " + elem.value;
                  }
               }
      });
      //load JSON data.
      barChart.loadJSON(json);
      $(this).next().hide();
  });
});
