document.addEventListener("DOMContentLoaded", function () {
  var zone = document.getElementById("drop");
  if (!zone) {
    return;
  }
  var input = zone.querySelector("input[type=file]");
  ["dragenter", "dragover"].forEach(function (name) {
    zone.addEventListener(name, function (event) {
      event.preventDefault();
      zone.classList.add("over");
    });
  });
  ["dragleave", "drop"].forEach(function (name) {
    zone.addEventListener(name, function (event) {
      event.preventDefault();
      zone.classList.remove("over");
    });
  });
  zone.addEventListener("drop", function (event) {
    input.files = event.dataTransfer.files;
  });
});
