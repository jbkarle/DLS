(function () {
    'use strict';

    angular.module('classifyImage', ['ngMaterial'])
        .directive('classifyImage', function () {
            return {
                scope: {
                    modelId: '@',
                    images: '<',
                    state: '<',
                    fileUrl: '<'
                },
                templateUrl: '/frontend/components/classification/image-2d/model/inference/classify-image/classify-image.html',
                controller: function ($scope, $mdDialog, appConfig, Upload, modelService, $window) {
                    var self = this;

                    const state = {
                        INIT: 'INIT',
                        LOADING: 'LOADING',
                        LOADED: 'LOADED'
                    };

                    this.$onInit = function () {
                        $scope.state = state.INIT;
                        $scope.images = [];
                        $scope.fileUrl = '';
                    };
                    

                    $scope.uploadFiles = function(file, errFiles) {
                        $scope.f = file;
                        $scope.errFile = errFiles && errFiles[0];
                        if (file) {
                            file.upload = Upload.upload({
                                url: 'model/uploadFile',
                                data: {file: file}
                            });

                            file.upload.then(function (response) {
                                
                                    file.result = response.data;
                                    console.log(response.data);
                                    $scope.state = state.LOADING;
                                    $scope.images.length = 0;

                                    var future = modelService.inference(response.data, $scope.modelId);
                                    processInferenceResult(future);
                                    
                               
                            }, function (response) {
                                if (response.status > 0)
                                    $scope.errorMsg = response.status + ': ' + response.data;
                            }, function (evt) {
                            file.progress = Math.min(100, parseInt(100.0 * 
                            evt.loaded / evt.total));
                            });
                        }
                        console.log("uploading file");
                    };
                    
                    $scope.choseImages = function (event) {
                        appConfig.fileManager.pickFile = true;
                        appConfig.fileManager.pickFolder = false;
                        appConfig.fileManager.singleSelection = false;
                        $mdDialog.show({
                            templateUrl: '/frontend/components/main/file-manager/file-manager.html',
                            parent: angular.element(document.body),
                            targetEvent: event,
                            clickOutsideToClose: false,
                            controller: function (scope, $mdDialog, $rootScope, $window, modelService) {

                                scope.select = function (answer) {
                                    $mdDialog.hide(answer);

                                    var images = [];
                                    $rootScope.selectedFiles.forEach(function (item, i, array) {
                                        console.log(item.model.fullPath(), item.model.name, item.model.type, item.model.size);
                                        images.push(item.model.fullPath());
                                    });

                                    if (images.length > 0) {
                                        $scope.state = state.LOADING;
                                        $scope.images.length = 0;

                                        var future = modelService.inference(images, $scope.modelId);
                                         processInferenceResult(future);
                                    } else {
                                        choseImageAlert();
                                    }
                                };

                                function choseImageAlert() {
                                    $mdDialog.show(
                                        $mdDialog.alert()
                                            .parent(angular.element(document.body))
                                            .title('Image Chooser')
                                            .textContent('Please, choose some image!')
                                            .ariaLabel('Image Chooser')
                                            .ok('OK')
                                    );
                                }

                                scope.cancel = function () {
                                    $mdDialog.cancel();
                                };
                            }
                        });
                    };

                    function showNClasses(images, classesNumber) {
                        var loadImageUrl = appConfig.util.loadImageUrl;
                        var i = 0;
                        images.forEach(function (result) {
                            var classifiedImage = {
                                'classProbabilities': result.classProbabilities.slice(0, classesNumber),
                                'imagePath': loadImageUrl + result.imagePath
                            };
                            $scope.images.push(classifiedImage);
                            i++;
                        });
                    }

                    function buildCSV(images) {
                        //csv header
                        var classes = [];
                        var csv = "path,";
                        var i = 0;
                        var classProbs = images[0].classProbabilities;
                        classProbs.forEach(function (classProb) {
                            classes.push(classProb[0]);
                        });

                        classes.sort();

                        classes.forEach(function (clazz) {
                            csv += clazz;
                            if (i < classes.length - 1) {
                                csv += ",";
                            } else {
                                csv += '\n';
                            }
                            i++;
                        });
                        //csv content
                        images.forEach(function (image) {
                            csv += image.imagePath + ',';
                            i = 0;
                            classes.forEach(function (className) {
                                image.classProbabilities.forEach(function (classProb) {
                                    if (classProb[0] == className) {
                                        csv += classProb[1];
                                        if (i < classes.length - 1) {
                                            csv += ",";
                                        }
                                        i++;
                                    }
                                })
                            });
                            csv += '\n';
                        });

                        return csv;
                    }
                    
                    function processInferenceResult(future){
                        future.then(function mySucces(response) {

                                    showNClasses(response.data.data, 8);

                                    //build reference to download
                                    var csv = buildCSV(response.data.data);
                                    var blob = new Blob([csv], {type: 'text/plain'});
                                    var url = $window.URL || $window.webkitURL;
                                    $scope.fileUrl = url.createObjectURL(blob);
                                    $scope.state = state.LOADED;
                                    }, function myError(response) {
                                            console.log(response);
                                    });
                    }
                }
            }
        });
})();