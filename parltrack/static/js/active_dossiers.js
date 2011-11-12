var featureList=["pivot","statistics"];
jQuery(document).ready(function() {
  jQuery( "#tabs" ).tabs();
  jQuery("#sortedlist").tablesorter({
    sortList: [[1,0],[0,0]],
    textExtraction: function(node) {
       var max='2020/12/31'
       var tmp=null;
       var d=jQuery(node).find('abbr');
       if(d.length==0) {
          if(jQuery(node).text().trim()=='') {
             return '999999999999';
          }
          return jQuery(node).text().trim();
       }
       var now=new Date();
       now=now.getFullYear()+'/'+zeroPad((1+now.getMonth()),2)+'/'+zeroPad(now.getDate(),2);
       for(var i=0; i<d.length; i++) {
          tmp=jQuery(d[i]).text().trim();
          //console.log([d, now,tmp,max]);
          if(tmp.split('/').length==3) {
             if(now<tmp && tmp<max) {
                //console.log('adf '+tmp);
                max=tmp;
             }
          }
       }
       //console.log(max.split('/').join(''));
       return max.split('/').join('');
    }
  });
});
var header = ["Type","Stage","Committe","Year","Month","Day"];
function cb() {
   var pivot = new
      OAT.Pivot("pivot_content",null,"pivot_page",header,data,[0,2],[1],[],4,{agg: 0, showEmpty: 0, type: 4});
}
function init() {
   OAT.Loader.loadFeatures(['pivot','statistics'], cb);
}
if(typeof(String.prototype.trim) === "undefined") { String.prototype.trim = function() {
      return String(this).replace(/^\s+|\s+$/g, '').replace(/\s+/,' ');
   };
}
function zeroPad(num,count) {
   var numZeropad = num + '';
   while(numZeropad.length < count) {
      numZeropad = "0" + numZeropad;
   }
   return numZeropad;
}
