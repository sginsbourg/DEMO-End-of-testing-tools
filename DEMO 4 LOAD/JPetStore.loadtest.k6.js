import http from 'k6/http';
import {
    check,
    sleep,
    group
} from 'k6';
import {
    parseHTML
} from 'k6/html';
// 1. Parameterization Data const keywords = ['bulldog', 'koi', 'poodle', 'parrot', 'dalmatian']; const itemIds = ['EST-1', 'EST-6', 'EST-13', 'EST-18'];
export const options = {
        vus: 5,
        duration: '10m',
        thresholds: {
            http_req_duration: ['p(95)<800'], // SLA: 95% of requests < 800ms http_req_failed: ['rate<0.02'], // SLA: Error rate < 2% }, };
            const BASE_URL = 'https://petstore.octoperf.com/actions';
            // 2. Correlation Helper
            function extractTokens(res) {
                const doc = parseHTML(res.body);
                return {
                    sourcePage: doc.find('input[name="_sourcePage"]').attr('value'),
                    fp: doc.find('input[name="__fp"]').attr('value'),
                };
            }
            export default function() {
                const keyword = keywords[Math.floor(Math.random() * keywords.length)];
                const itemId = itemIds[Math.floor(Math.random() * itemIds.length)];
                group('Transactional_Buyer_Journey', function() { // Discovery http.get(`${BASE_URL}/Catalog.action?searchProducts=&keyword=${keyword}`);
                            // Login with Correlation let res = http.get(`${BASE_URL}/Account.action?signonForm=`); let tokens = extractTokens(res); res = http.post(`${BASE_URL}/Account.action`, { username: 'j2ee', password: 'j2ee', signon: 'Login', _sourcePage: tokens.sourcePage, __fp: tokens.fp, });
                            // Cart POST (Update Quantity) http.get(`${BASE_URL}/Cart.action?addItemToCart=&workingItemId=${itemId}`); res = http.get(`${BASE_URL}/Cart.action?viewCart=`); tokens = extractTokens(res); let payload = { updateCartQuantities: 'Update Cart', _sourcePage: tokens.sourcePage, __fp: tokens.fp }; payload[itemId] = '5'; http.post(`${BASE_URL}/Cart.action`, payload);
                            // Final Order POST res = http.get(`${BASE_URL}/Order.action?newOrderForm=`); tokens = extractTokens(res); http.post(`${BASE_URL}/Order.action`, { confirm: 'Confirm', _sourcePage: tokens.sourcePage, __fp: tokens.fp, }); });
                            sleep(Math.random() * 3 + 1); // Randomized think time }