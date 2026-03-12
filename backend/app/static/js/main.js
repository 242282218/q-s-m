(function() {
  'use strict';

  var header = document.querySelector('.site-header');
  var lastScrollY = 0;
  var ticking = false;

  function updateHeader() {
    var scrollY = window.scrollY || window.pageYOffset;
    
    if (scrollY > 50) {
      header.classList.add('scrolled');
    } else {
      header.classList.remove('scrolled');
    }
    
    lastScrollY = scrollY;
    ticking = false;
  }

  function onScroll() {
    if (!ticking) {
      window.requestAnimationFrame(updateHeader);
      ticking = true;
    }
  }

  window.addEventListener('scroll', onScroll, { passive: true });
  
  updateHeader();

  // 横向滚动交互
  var posterRows = document.querySelectorAll('.posters-row');
  
  posterRows.forEach(function(row) {
    var isDown = false;
    var startX = 0;
    var scrollLeft = 0;

    row.addEventListener('mousedown', function(e) {
      isDown = true;
      row.classList.add('is-dragging');
      startX = e.pageX - row.offsetLeft;
      scrollLeft = row.scrollLeft;
    });

    row.addEventListener('mouseleave', function() {
      isDown = false;
      row.classList.remove('is-dragging');
    });

    row.addEventListener('mouseup', function() {
      isDown = false;
      row.classList.remove('is-dragging');
    });

    row.addEventListener('mousemove', function(e) {
      if (!isDown) return;
      e.preventDefault();
      var x = e.pageX - row.offsetLeft;
      var walk = (x - startX) * 2;
      row.scrollLeft = scrollLeft - walk;
    });

    // 触摸支持
    row.addEventListener('touchstart', function(e) {
      startX = e.touches[0].pageX - row.offsetLeft;
      scrollLeft = row.scrollLeft;
    }, { passive: true });

    row.addEventListener('touchmove', function(e) {
      var x = e.touches[0].pageX - row.offsetLeft;
      var walk = (x - startX) * 1.5;
      row.scrollLeft = scrollLeft - walk;
    }, { passive: true });
  });
})();
