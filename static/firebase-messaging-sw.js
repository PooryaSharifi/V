importScripts('https://www.gstatic.com/firebasejs/6.0.2/firebase-app.js');
importScripts('https://www.gstatic.com/firebasejs/6.0.2/firebase-messaging.js');

firebase.initializeApp({
  apiKey: "AIzaSyBYZWVJBC033SPzHhyyJmVkQfo1U-okYOE",
  authDomain: "express-1516177074533.firebaseapp.com",
  databaseURL: "https://express-1516177074533.firebaseio.com",
  projectId: "express-1516177074533",
  storageBucket: "express-1516177074533.appspot.com",
  messagingSenderId: "197435492753",
  appId: "1:197435492753:web:6c0dcbb5a87b9f7b"
});

const messaging = firebase.messaging();
// messaging.usePublicVapidKey("BLfKOKE-XahtbbEDFTiF4MJAvQHCKCfYvukiS5Nf8k2hnF5l_6U5ytCUhomzzChjLrzykeWxfF3lLEXZLrSmRD8");
messaging.setBackgroundMessageHandler(function(payload) {
  console.log('[firebase-messaging-sw.js] Received background message ', payload);
  // Customize notification here
  var notificationTitle = 'Background Message Title';
  var notificationOptions = {
    body: 'Background Message body.',
    icon: 'http://localhost:5000/static/favicon.png'
  };

  return self.registration.showNotification(notificationTitle, notificationOptions);
});