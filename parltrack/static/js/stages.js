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
   '': '#EE1C23',
   '': '#EE1C23',
   '': '#009900',
   '': '#0054A5',
   '': '#6699FF',
   '': '#3099DB',
   '': '#990000',
   '': '#FFD700',
   '': '#fff',
   '': '#fff',
   '': '#000',
   '': '#F7AF20',
   '': '#5d4fa5',
   '': '#2ca8be',
}
jQuery(document).ready(function() {
      //init BarChart
      var barChart = new $jit.BarChart({
         //id of the visualization container
         injectInto: 'stages-graph',
         //whether to add animations
         animate: true,
         //horizontal or vertical barcharts
         orientation: 'vertical',
         height: 300,
         //width: 800,
         //bars separation
         //barsOffset: 5,
         //visualization offset
         Margin: {
             top: 5,
             left: 5,
             right: 5,
             bottom: 5
         },
         //labels offset position
         labelOffset: 15,
         //bars style
         type: useGradients? 'stacked:gradient' : 'stacked',
         //whether to show the aggregation of the values
         showAggregates: true,
         //whether to show the labels for the bars
         showLabels: true,
         //labels style
         Label: {
            type: 'HTML', //labelType, //Native or HTML
            size: 10,
            family: 'Verdana',
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
});
