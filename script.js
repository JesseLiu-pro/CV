const body = document.body;
const header = document.getElementById('site-header');
const languageButtons = document.querySelectorAll('[data-language]');
const viewButtons = document.querySelectorAll('[data-view]');
const viewPanels = document.querySelectorAll('.view-panel');
const themeColor = document.getElementById('theme-color');
const preferredLanguage = 'en';

function setLanguage(language) {
  const nextLanguage = language === 'zh' ? 'zh' : 'en';
  body.classList.toggle('lang-zh', nextLanguage === 'zh');
  body.classList.toggle('lang-en', nextLanguage === 'en');
  document.documentElement.lang = nextLanguage === 'zh' ? 'zh-CN' : 'en';
  languageButtons.forEach((button) => {
    button.setAttribute('aria-pressed', String(button.dataset.language === nextLanguage));
  });
}

languageButtons.forEach((button) => {
  button.addEventListener('click', () => setLanguage(button.dataset.language));
});

setLanguage(preferredLanguage);

function setView(view) {
  const nextView = view === 'life' ? 'life' : 'work';
  body.classList.toggle('view-life', nextView === 'life');
  body.classList.toggle('view-work', nextView === 'work');
  themeColor.setAttribute('content', nextView === 'life' ? '#4b351b' : '#102319');
  viewButtons.forEach((button) => {
    const selected = button.dataset.view === nextView;
    button.setAttribute('aria-selected', String(selected));
    button.tabIndex = selected ? 0 : -1;
  });
  viewPanels.forEach((panel) => {
    const selected = panel.id === `${nextView}-view`;
    panel.hidden = !selected;
    panel.classList.toggle('is-entering', selected);
    if (selected) {
      window.setTimeout(() => panel.classList.remove('is-entering'), 500);
      panel.querySelectorAll('.reveal:not(.is-visible)').forEach((element) => observer.observe(element));
    }
  });
  document.querySelectorAll('.desktop-nav a').forEach((link) => {
    link.toggleAttribute('hidden', nextView === 'life');
  });
  history.replaceState(null, '', nextView === 'life' ? '#life' : '#top');
  document.getElementById(nextView === 'life' ? 'life-view' : 'work-view').scrollIntoView({ behavior: 'smooth', block: 'start' });
}

viewButtons.forEach((button, index) => {
  button.addEventListener('click', () => setView(button.dataset.view));
  button.addEventListener('keydown', (event) => {
    if (!['ArrowLeft', 'ArrowRight'].includes(event.key)) return;
    event.preventDefault();
    const nextIndex = event.key === 'ArrowRight' ? (index + 1) % viewButtons.length : (index - 1 + viewButtons.length) % viewButtons.length;
    viewButtons[nextIndex].focus();
    setView(viewButtons[nextIndex].dataset.view);
  });
});

function updateHeader() {
  header.classList.toggle('is-scrolled', window.scrollY > 40);
}

updateHeader();
window.addEventListener('scroll', updateHeader, { passive: true });

const observer = new IntersectionObserver((entries) => {
  entries.forEach((entry) => {
    if (entry.isIntersecting) {
      entry.target.classList.add('is-visible');
      observer.unobserve(entry.target);
    }
  });
}, { threshold: 0.12, rootMargin: '0px 0px -40px' });

document.querySelectorAll('.reveal').forEach((element) => observer.observe(element));
if (window.location.hash === '#life') {
  setView('life');
}
document.getElementById('year').textContent = new Date().getFullYear();

const imageLightbox = document.getElementById('image-lightbox');
const lightboxImage = imageLightbox?.querySelector('img');
const lightboxCaption = document.getElementById('lightbox-caption');

document.querySelectorAll('[data-lightbox-src]').forEach((button) => {
  button.addEventListener('click', () => {
    if (!imageLightbox || !lightboxImage || !lightboxCaption) return;
    lightboxImage.src = button.dataset.lightboxSrc;
    lightboxImage.alt = button.querySelector('img')?.alt || '';
    lightboxCaption.textContent = button.dataset.lightboxCaption || '';
    body.classList.add('lightbox-open');
    imageLightbox.showModal();
  });
});

const closeImageLightbox = () => {
  imageLightbox?.close();
  body.classList.remove('lightbox-open');
};

imageLightbox?.querySelector('.lightbox-close')?.addEventListener('click', closeImageLightbox);
imageLightbox?.addEventListener('click', (event) => {
  if (event.target === imageLightbox) closeImageLightbox();
});
imageLightbox?.addEventListener('close', () => body.classList.remove('lightbox-open'));

window.addEventListener('DOMContentLoaded', () => {
  if (window.lucide) {
    window.lucide.createIcons({ strokeWidth: 1.7 });
  }
});

const cursorDot = document.getElementById('cursor-dot');
const finePointer = window.matchMedia('(pointer: fine)');
const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');

if (cursorDot && finePointer.matches && !reducedMotion.matches) {
  window.addEventListener('pointermove', (event) => {
    if (event.pointerType && event.pointerType !== 'mouse') return;
    body.classList.add('cursor-ready');
    cursorDot.style.opacity = '1';
    cursorDot.style.transform = `translate3d(${event.clientX - 5}px, ${event.clientY - 5}px, 0)`;
  }, { passive: true });
  document.documentElement.addEventListener('mouseleave', () => { cursorDot.style.opacity = '0'; });
}

document.querySelectorAll('[data-drag-scroll]').forEach((rail) => {
  let isDragging = false;
  let startX = 0;
  let startScrollLeft = 0;

  rail.addEventListener('pointerdown', (event) => {
    if (event.pointerType !== 'mouse' || event.button !== 0) return;
    isDragging = true;
    startX = event.clientX;
    startScrollLeft = rail.scrollLeft;
    rail.classList.add('is-dragging');
    rail.setPointerCapture(event.pointerId);
  });

  rail.addEventListener('pointermove', (event) => {
    if (!isDragging) return;
    event.preventDefault();
    rail.scrollLeft = startScrollLeft - (event.clientX - startX);
  });

  const stopDragging = (event) => {
    if (!isDragging) return;
    isDragging = false;
    rail.classList.remove('is-dragging');
    if (rail.hasPointerCapture(event.pointerId)) rail.releasePointerCapture(event.pointerId);
  };

  rail.addEventListener('pointerup', stopDragging);
  rail.addEventListener('pointercancel', stopDragging);
  rail.addEventListener('keydown', (event) => {
    if (!['ArrowLeft', 'ArrowRight'].includes(event.key)) return;
    event.preventDefault();
    rail.scrollBy({ left: event.key === 'ArrowRight' ? 320 : -320, behavior: 'smooth' });
  });
});
