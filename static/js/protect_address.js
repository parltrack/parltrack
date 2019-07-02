$(document).ready(function() {
   $('.protected_address').each(function() {
      var a=$(this).data('key');
      var b=a.split("").sort().join("");
      var c=$(this).data('ctext');
      var d="";
      for(var e=0;e<c.length;e++)d+=b.charAt(a.indexOf(c.charAt(e)));
      $(this).html("<a href=\"mailto:"+d+"\">"+d+"</a>");
   });
});
