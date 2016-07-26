'use strict';


angular.module('constructorCore', [
  'palette',
  'graph'
]);

var editorDefinition = {
	templateUrl: 'frontend/components/builder/constructor/core.html',
	controller: ConstructorController,
	controllerAs: 'cstr',
	bindings: {

	}
}

angular.module('constructorCore')
	.service('constructorService', ConstructorService)
	.component('constructor', editorDefinition);

function ConstructorService() {
	var categories = [
		{
        	name : 'input',
    	},
    	{
        	name : 'output',
    	},
    ];

    var paletteElements = [
		{
		    id: 1,
			name : 'websocket',
			content : 'web',
			category : 'input',
			pos: {x: 100, y: 200},
		}, {
		    id: 2,
			name : 'socket',
			content : 'socket',
			category : 'input',
			pos: {x: 300, y: 300},
		}, {
		    id: 3,
			name : 'db',
			content : 'db',
			category : 'output',
			pos: {x: 300, y: 500},
		},
	];

  	var nodes = [
		{
		    id: 1,
			name : 'websocket',
			content : 'web',
			category : 'input',
			pos: {x: 100, y: 200},
			wires: [
			    2
			]
		}, {
		    id: 2,
			name : 'socket',
			content : 'socket',
			category : 'input',
			pos: {x: 300, y: 300},
			wires: [
			    3, 1
			]
		}, {
		    id: 3,
			name : 'db',
			content : 'db',
			category : 'output',
			pos: {x: 300, y: 500},
		},
	];

    this.getCategories= function() {
    	return categories;
    };

    this.getPaletteElements= function() {
    	return paletteElements;
    };

	this.getNodes = function() {
    	return nodes;
    };
}

function ConstructorController($scope, $rootScope) {

	this.$onInit = function() {

    };
}



