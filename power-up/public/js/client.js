/* global TrelloPowerUp */

var Promise = TrelloPowerUp.Promise;

var BLACK_ROCKET_ICON = 'https://cdn.glitch.com/7913d87b-6629-460a-aedc-798b90d3ddcc%2Fsprint_burndown_chart_logo.png?v=1588638210356';

TrelloPowerUp.initialize({
	'board-buttons': function(t, options) {
      return [{
	      icon: BLACK_ROCKET_ICON,
	 		  text: 'Sprint Burn Down',
        callback: function (t, opts) {
            return t.popup({
                title: 'Configure',
                url: './mainpage.html',
                // height: 350
            })
          }
        }
	 	  ];
    }
});
