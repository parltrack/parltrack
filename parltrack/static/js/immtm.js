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

var initTM=function(json) {
  //init data
  var tm = new $jit.TM.Squarified({  
     //where to inject the visualization  
     injectInto: 'immunity-treemap',  
     //parent box title heights  
     titleHeight: 25,  
     //enable animations  
     animate: animate,
     //box offsets  
     offset: 1,  
     constrained: true,
     levelsToShow: 1,
     //Attach left and right click events  
     Events: {  
       enable: true,  
       onClick: function(node) {  
         if(node) tm.enter(node);  
       },  
       onRightClick: function() {  
         tm.out();  
       }  
     },  
     duration: 1000,  
     //Enable tips  
     Tips: {  
       enable: true,  
       //add positioning offsets  
       offsetX: 20,  
       offsetY: 20,  
       //implement the onShow method to  
       //add content to the tooltip when a node  
       //is hovered  
       onShow: function(tip, node, isLeaf, domElement) {  
         var html = "<div class=\"tip-title\">" + node.name   
           + "</div><div class=\"tip-text\">";  
         var data = node.data;  
         html += "cases: " + data.$area;  
         tip.innerHTML =  html;   
       }    
     },  
     //Add the name of the node in the correponding label  
     //This method is called once, on label creation.  
     onCreateLabel: function(domElement, node){  
         domElement.innerHTML = node.name;  
         var style = domElement.style;  
         style.display = '';  
         style.border = '1px solid transparent';  
         domElement.onmouseover = function() {  
           style.border = '1px solid #9FD4FF';  
         };  
         domElement.onmouseout = function() {  
           style.border = '1px solid transparent';  
         };  
     },
   });  
   tm.loadJSON(json);  
   tm.refresh();  
};

