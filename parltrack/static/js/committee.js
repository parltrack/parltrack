$(function() {
	$( "#tabs" ).tabs();
   $("#sortedlist").tablesorter();
   $('#sortedlist').tableFilter({enableCookies: false});
   $("#sortedlist2").tablesorter({
      sortList: [[2,0],[0,1]],
      textExtraction: function(node) {
         var max='2020/12/31'
         var tmp=null;
         var d=$(node).find('abbr');
         if(d.length==0) {
            if($(node).text().trim()=='') {
               return '99999999';
            }
            return $(node).text().trim();
         }
         var now=new Date();
         now=now.getFullYear()+'/'+zeroPad((1+now.getMonth()),2)+'/'+zeroPad(now.getDate(),2);
         for(var i=0; i<d.length; i++) {
            tmp=$(d[i]).text().trim();
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
   $('#sortedlist2').tableFilter({enableCookies: false});
});
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
